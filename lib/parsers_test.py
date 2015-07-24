#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for parsers."""

# pylint: disable=unused-import
from grr import parsers
# pylint: enable=unused-import

from grr.lib import artifact_registry
from grr.lib import artifact_test
from grr.lib import flags
from grr.lib import parsers
from grr.lib import rdfvalue
from grr.lib import test_lib


class ArtifactParserTests(test_lib.GRRBaseTest):
  """Test parsers validate."""

  def ValidateParser(self, parser):
    """Validate a parser is well defined."""
    for artifact_to_parse in parser.supported_artifacts:
      art_obj = artifact_registry.REGISTRY.GetArtifact(
          artifact_to_parse)
      if art_obj is None:
        raise parsers.ParserDefinitionError(
            "Artifact parser %s has an invalid artifact"
            " %s. Artifact is undefined" %
            (parser.__name__, artifact_to_parse))

    for out_type in parser.output_types:
      if out_type not in rdfvalue.RDFValue.classes:
        raise parsers.ParserDefinitionError(
            "Artifact parser %s has an invalid output "
            "type %s." % (parser.__name__, out_type))

    if parser.process_together:
      if not hasattr(parser, "ParseMultiple"):
        raise parsers.ParserDefinitionError(
            "Parser %s has set process_together, but "
            "has not defined a ParseMultiple method." %
            parser.__name__)

    # Additional, parser specific validation.
    parser.Validate()

  def testValidation(self):
    """Ensure all parsers pass validation."""
    artifact_test.ArtifactTest.LoadTestArtifacts()
    for p_cls in parsers.Parser.classes:
      parser = parsers.Parser.classes[p_cls]
      self.ValidateParser(parser)


def main(argv):
  test_lib.main(argv)

if __name__ == "__main__":
  flags.StartMain(main)
