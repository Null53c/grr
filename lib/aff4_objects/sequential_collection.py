#!/usr/bin/env python
"""A collection of records stored sequentially.
"""

import random

from grr.lib import aff4
from grr.lib import data_store
from grr.lib import rdfvalue
from grr.lib import utils

from grr.lib.rdfvalues import protodict as rdf_protodict


class SequentialCollection(aff4.AFF4Object):
  """A sequential collection of RDFValues.

  This class supports the writing of individual RDFValues and the sequential
  reading of them.

  """

  # The type which we store, subclasses must set this to a subclass of RDFValue.
  RDF_TYPE = None

  # The attribute (column) where we store value.
  ATTRIBUTE = "aff4:sequential_value"

  # The largest possible suffix - maximum value expressible by 6 hex digits.
  MAX_SUFFIX = 2**24 - 1

  def _MakeURN(self, timestamp, suffix=None):
    if suffix is None:
      # Disallow 0 so that subtracting 1 from a normal suffix doesn't require
      # special handling.
      suffix = random.randint(1, self.MAX_SUFFIX)
    return self.urn.Add("Results").Add("%016x.%06x" % (timestamp, suffix))

  def _ParseURN(self, urn):
    string_urn = utils.SmartUnicode(urn)
    if len(string_urn) < 31 or string_urn[-7] != ".":
      return None
    return (int(string_urn[-23:-7], 16), int(string_urn[-6:], 16))

  def Add(self, rdf_value, timestamp=None, suffix=None, **kwargs):
    """Adds an rdf value to the collection.

    Adds an rdf value to the collection. Does not require that the collection
    be locked.

    Args:
      rdf_value: The rdf value to add to the collection.

      timestamp: The timestamp (in microseconds) to store the rdf value
          at. Defaults to the current time.

      suffix: A 'fractional timestamp' suffix to reduce the chance of
          collisions. Defaults to a random number.

      **kwargs: Keyword arguments to pass through to the underlying database
        call.

    Raises:
      ValueError: rdf_value has unexpected type.

    """
    if not isinstance(rdf_value, self.RDF_TYPE):
      raise ValueError("This collection only accepts values of type %s." %
                       self.RDF_TYPE.__name__)

    if timestamp is None:
      timestamp = rdfvalue.RDFDatetime().Now()

    if isinstance(timestamp, rdfvalue.RDFDatetime):
      timestamp = timestamp.AsMicroSecondsFromEpoch()

    result_subject = self._MakeURN(timestamp, suffix)
    data_store.DB.Set(result_subject,
                      self.ATTRIBUTE,
                      rdf_value.SerializeToString(),
                      timestamp=timestamp,
                      token=self.token,
                      **kwargs)

  def Scan(self, after_timestamp=None, include_suffix=False, max_records=None):
    """Scans for stored records.

    Scans through the collection, returning stored values ordered by timestamp.

    Args:

      after_timestamp: If set, only returns values recorded after timestamp.

      include_suffix: If true, the timestamps returned are pairs of the form
        (micros_since_epoc, suffix) where suffix is a 24 bit random refinement
        to avoid collisions. Otherwise only micros_since_epoc is returned.

      max_records: The maximum number of records to return. Defaults to
        unlimited.

    Yields:
      Pairs (timestamp, rdf_value), indicating that rdf_value was stored at
      timestamp.

    """
    after_urn = None
    if after_timestamp is not None:
      if isinstance(after_timestamp, tuple):
        suffix = after_timestamp[1]
        after_timestamp = after_timestamp[0]
      else:
        suffix = self.MAX_SUFFIX
      after_urn = self._MakeURN(after_timestamp, suffix=suffix)

    for subject, timestamp, value in data_store.DB.ScanAttribute(
        self.urn.Add("Results"),
        self.ATTRIBUTE,
        after_urn=after_urn,
        max_records=max_records,
        token=self.token):
      if include_suffix:
        yield (self._ParseURN(subject),
               self.RDF_TYPE(value))  # pylint: disable=not-callable
      else:
        yield (timestamp,
               self.RDF_TYPE(value))  # pylint: disable=not-callable


class IndexedSequentialCollection(SequentialCollection):
  """An indexed sequential collection of RDFValues.

  Adds an index to SequentialCollection, making it efficient to find the number
  of records present, and to find a particular record number.

  IMPLEMENTATION NOTE: The index is created lazily, and for records older than
    INDEX_WRITE_DELAY.
  """

  # How many records between index entries. Subclasses may change this.  The
  # full index must fit comfortably in RAM, default is meant to be reasonable
  # for collections of up to ~1b small records. (Assumes we can have ~1m index
  # points in ram, and that reading 1k records is reasonably fast.)

  INDEX_SPACING = 1024

  # An attribute name of the form "index:sc_<i>" at timestamp <t> indicates that
  # the item with record number i was stored at timestamp t. The timestamp
  # suffix is stored as the value.

  INDEX_ATTRIBUTE_PREFIX = "index:sc_"

  # The time to wait before creating an index for a record - hacky defense
  # against the correct index changing due to a late write.

  INDEX_WRITE_DELAY = rdfvalue.Duration("5m")

  def __init__(self, urn, **kwargs):
    super(IndexedSequentialCollection, self).__init__(urn, **kwargs)
    self._index = None

  def _ReadIndex(self):
    self._index = {0: (0, 0)}
    self._max_indexed = 0
    for (attr, value, ts) in data_store.DB.ResolvePrefix(
        self.urn,
        self.INDEX_ATTRIBUTE_PREFIX,
        token=self.token):
      i = int(attr[len(self.INDEX_ATTRIBUTE_PREFIX):], 16)
      self._index[i] = (ts, int(value, 16))
      self._max_indexed = max(i, self._max_indexed)

  def _MaybeWriteIndex(self, i, ts):
    """Write index marker i."""
    if i > self._max_indexed and i % self.INDEX_SPACING == 0:
      # We only write the index if the timestamp is more than 5 minutes in the
      # past: hacky defense against a late write changing the count.
      if ts[0] < (rdfvalue.RDFDatetime().Now() -
                  self.INDEX_WRITE_DELAY).AsMicroSecondsFromEpoch():
        data_store.DB.Set(self.urn,
                          self.INDEX_ATTRIBUTE_PREFIX + "%08x" % i,
                          "%06x" % ts[1],
                          ts[0],
                          token=self.token,
                          replace=True)
        self._index[i] = ts
        self._max_indexed = max(i, self._max_indexed)

  def _IndexedScan(self, i, max_records=None):
    """Scan records starting with index i."""
    if not self._index:
      self._ReadIndex()

    # The record number that we will read next.
    idx = 0
    # The timestamp that we will start reading from.
    start_ts = 0
    if i >= self._max_indexed:
      start_ts = max(
          (0, 0), (self._index[self._max_indexed][0],
                   self._index[self._max_indexed][1] - 1))
      idx = self._max_indexed
    else:
      try:
        possible_idx = i - i % self.INDEX_SPACING
        start_ts = (max(0, self._index[possible_idx][0]),
                    self._index[possible_idx][1] - 1)
        idx = possible_idx
      except KeyError:
        pass

    if max_records is not None:
      max_records += i - idx

    for (ts, value) in self.Scan(after_timestamp=start_ts,
                                 max_records=max_records,
                                 include_suffix=True):
      self._MaybeWriteIndex(idx, ts)
      if idx >= i:
        yield (idx, ts, value)
      idx += 1

  def GenerateItems(self, offset=0):
    for (idx, _, value) in self._IndexedScan(offset):
      yield (idx, value)

  def __getitem__(self, index):
    if index >= 0:
      for (_, _, value) in self._IndexedScan(index, max_records=1):
        return value
      return None
    else:
      raise RuntimeError("Index must be >= 0")

  def CalculateLength(self):
    if not self._index:
      self._ReadIndex()
    last_idx = self._max_indexed
    for (i, _, _) in self._IndexedScan(last_idx):
      last_idx = i
    return last_idx + 1

  def __len__(self):
    return self.CalculateLength()


class GeneralIndexedCollection(IndexedSequentialCollection):
  """An indexed sequential collection of RDFValues with different types."""
  RDF_TYPE = rdf_protodict.EmbeddedRDFValue

  def Add(self, rdf_value, **kwargs):
    super(GeneralIndexedCollection, self).Add(
        rdf_protodict.EmbeddedRDFValue(payload=rdf_value),
        **kwargs)

  def Scan(self, **kwargs):
    for (timestamp, rdf_value) in super(GeneralIndexedCollection, self).Scan(
        **kwargs):
      yield (timestamp, rdf_value.payload)
