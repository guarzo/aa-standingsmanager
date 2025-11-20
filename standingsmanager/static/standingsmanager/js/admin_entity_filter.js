/**
 * Admin form JavaScript to filter eve_entity dropdown based on entity_type selection
 */

(function($) {
    'use strict';

    $(document).ready(function() {
        var $entityTypeField = $('#id_entity_type');
        var $eveEntityField = $('#id_eve_entity');

        // Check if both fields exist
        if ($eveEntityField.length && $entityTypeField.length) {
            setupAutocompleteFilter();
        }

        function setupAutocompleteFilter() {
            // Store the original select2 configuration
            var originalAjaxUrl = null;
            var originalConfig = null;

            // Wait for select2 to be initialized by Django admin
            setTimeout(function() {
                var $select2 = $eveEntityField.data('select2');
                if ($select2 && $select2.options && $select2.options.ajax) {
                    originalAjaxUrl = $select2.options.ajax.url;
                    originalConfig = $.extend(true, {}, $select2.options);
                }
            }, 100);

            // Handle entity_type change
            $entityTypeField.on('change', function() {
                var selectedType = $entityTypeField.val();

                // Wait for select2 to be ready
                setTimeout(function() {
                    var $select2 = $eveEntityField.data('select2');

                    if (!$select2) {
                        return;
                    }

                    // Get the autocomplete URL
                    var ajaxUrl = originalAjaxUrl;
                    if (!ajaxUrl && $select2.options && $select2.options.ajax) {
                        ajaxUrl = $select2.options.ajax.url;
                    }

                    if (!ajaxUrl) {
                        return;
                    }

                    // Destroy and reinitialize select2 with category filter
                    $eveEntityField.select2('destroy');

                    // Map entity types to EveEntity categories
                    var categoryMap = {
                        'character': 'character',
                        'corporation': 'corporation',
                        'alliance': 'alliance'
                    };

                    var category = categoryMap[selectedType];

                    // Reinitialize with category filter
                    var newConfig = {
                        ajax: {
                            url: ajaxUrl,
                            dataType: 'json',
                            delay: 250,
                            data: function(params) {
                                var queryParams = {
                                    term: params.term,
                                    page: params.page || 1
                                };
                                // Add category filter if entity_type is selected
                                if (category) {
                                    queryParams.category = category;
                                }
                                return queryParams;
                            },
                            processResults: function(data) {
                                return {
                                    results: data.results || [],
                                    pagination: {
                                        more: data.pagination ? data.pagination.more : false
                                    }
                                };
                            },
                            cache: true
                        },
                        placeholder: 'Search for an entity...',
                        minimumInputLength: 0,
                        allowClear: true
                    };

                    $eveEntityField.select2(newConfig);

                    // Clear selection when entity_type changes
                    $eveEntityField.val(null).trigger('change');
                }, 50);
            });
        }
    });
})(django.jQuery);
