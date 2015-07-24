'use strict';

goog.provide('grrUi.forms.semanticValueFormDirective');
goog.provide('grrUi.forms.semanticValueFormDirective.SemanticValueFormController');
goog.provide('grrUi.forms.semanticValueFormDirective.SemanticValueFormDirective');


/**
 * @type {Object<string,
 *     function(!angular.Scope, function(Object, !angular.Scope=)=):Object>}
 * Cache for templates used by semantic value directive.
 */
grrUi.forms.semanticValueFormDirective.templatesCache = {};


/**
 * Clears cached templates.
 *
 * @export
 */
grrUi.forms.semanticValueFormDirective.clearCaches = function() {
  grrUi.forms.semanticValueFormDirective.templatesCache = {};
};


/**
 * Controller for SemanticValueFormDirective.
 *
 * @constructor
 * @param {!angular.Scope} $scope
 * @param {!angular.$compile} $compile
 * @param {!angular.JQLite} $element
 * @param {!grrUi.core.semanticRegistry.SemanticRegistryService}
 *     grrSemanticFormDirectivesRegistryService
 * @ngInject
 */
grrUi.forms.semanticValueFormDirective.SemanticValueFormController = function(
    $scope, $compile, $element, grrSemanticFormDirectivesRegistryService) {
  /** @private {!angular.Scope} */
  this.scope_ = $scope;

  /** @private {!angular.$compile} */
  this.compile_ = $compile;

  /** @private {!angular.JQLite} */
  this.element_ = $element;

  /** @private {!grrUi.core.semanticRegistry.SemanticRegistryService} */
  this.grrSemanticFormDirectivesRegistryService_ =
      grrSemanticFormDirectivesRegistryService;

  this.scope_.$watch('value.type', this.onValueTypeChange_.bind(this));
};
var SemanticValueFormController =
    grrUi.forms.semanticValueFormDirective.SemanticValueFormController;


/**
 * Handles value type changes.
 *
 * @param {?string} newValue
 * @private
 */
SemanticValueFormController.prototype.onValueTypeChange_ = function(newValue) {
  this.element_.html('');

  if (angular.isUndefined(newValue)) {
    return;
  }

  var updateElement = function(tmpl) {
    if (angular.isDefined(tmpl)) {
      tmpl(this.scope_, function(cloned, opt_scope) {
        this.element_.append(cloned);
      }.bind(this));
    } else {
      this.element_.text('Can\'t handle type: ' + this.value['type']);
    }
  }.bind(this);

  var templatesCache = grrUi.forms.semanticValueFormDirective.templatesCache;
  var value = this.scope_.value;
  var template = templatesCache[value['type']];
  if (angular.isUndefined(template)) {
    this.compileSingleTypedValueTemplate_(value).then(function(template) {
      templatesCache[value['type']] = template;
      updateElement(template);
    }.bind(this));
  } else {
    updateElement(template);
  }
};

/**
 * Converts camelCaseStrings to dash-delimited-strings.
 *
 * @param {string} directiveName String to be converted.
 * @return {string} Converted string.
 * @export
 */
SemanticValueFormController.prototype.camelCaseToDashDelimited = function(
    directiveName) {
  return directiveName.replace(/([a-z\d])([A-Z])/g, '$1-$2').toLowerCase();
};


/**
 * Compiles a template for a given single value.
 *
 * @param {Object} value Value to compile the template for.
 * @return {function(!angular.Scope, function(Object,
 *     !angular.Scope=)=):Object} Compiled template.
 * @private
 */
SemanticValueFormController.prototype
    .compileSingleTypedValueTemplate_ = function(value) {

  var successHandler = function success(directive) {
    var element = angular.element('<span />');

    element.html('<' + this.camelCaseToDashDelimited(directive.directive_name) +
        ' metadata="metadata" value="value" />');
    return this.compile_(element);
  }.bind(this);

  var failureHandler = function failure() {
    var element = angular.element('<span />');

    element.html('<p class="form-control-static">No directive ' +
        'for type: {$ value.type $}.</p>');
    return this.compile_(element);
  }.bind(this);

  return this.grrSemanticFormDirectivesRegistryService_.
      findDirectiveForType(value['type']).then(
          successHandler, failureHandler);
};


/**
 * SemanticValueFormDirective renders a form corresponding to a given semantic
 * RDF type.
 *
 * @return {!angular.Directive} Directive definition object.
 */
grrUi.forms.semanticValueFormDirective.SemanticValueFormDirective = function() {
  return {
    restrict: 'E',
    scope: {
      value: '=',
      metadata: '=?'
    },
    controller: SemanticValueFormController,
    controllerAs: 'controller'
  };
};


/**
 * Name of the directive in Angular.
 *
 * @const
 * @export
 */
grrUi.forms.semanticValueFormDirective.SemanticValueFormDirective
    .directive_name = 'grrFormValue';
