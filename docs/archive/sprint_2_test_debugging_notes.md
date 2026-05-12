# Sprint 2 - Test Debugging Notes - test_graph_flow_brief_ok

**Date:** 2025-05-30
**Test File:** `tests/integration/test_template_generation_graph.py`
**Test Case:** `test_graph_flow_brief_ok`

**Goal:**
Successfully mock the methods `mjml_service.generate_mjml_node` and `mjml_service.validate_and_compile_mjml_node` to test the "brief is OK" path of the template generation graph, expecting the graph to proceed through mocked successful image generation, MJML generation, and MJML validation stages. This test uses the `MemorySaver` checkpointer.

**Observed Issue:**
The test consistently fails with `AssertionError: Expected 'generate_mjml_node' to have been called once. Called 0 times.` (and subsequently for `validate_and_compile_mjml_node`).
Stdout from the test execution indicates that the graph flow proceeds as if the real `mjml_service` methods are being called, not the mocked versions. Specifically, the `last_operation_status` in the state reflects statuses set by the real methods rather than the specific statuses set by the mock side effects.

**Patching Attempts for `mjml_service` methods (all unsuccessful for this test):**

1.  **Patching methods on the `mjml_service` instance imported into the test file:**
    *   Example: `@patch.object(mjml_service, 'generate_mjml_node', ...)` where `mjml_service` was `from mailwright.graphs.template_generation_graph import mjml_service`.
    *   Result: Mocks not called.

2.  **Patching methods on the `MJMLService` class at its source definition:**
    *   Example: `@patch.object(MJMLService, 'generate_mjml_node', ...)` where `MJMLService` was `from mailwright.core_services.mjml_service import MJMLService`.
    *   Result: Mocks not called.

3.  **Patching methods on the `mjml_service` instance as it exists within the `mailwright.graphs.template_generation_graph` module (targeting the name used by `create_graph_builder`):**
    *   Example: `@patch('mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node', ...)`
    *   Result: Mocks not called. This was the most recent attempt.

**Successfully Working Mocks in the Same Test Environment:**
*   The `analyze_brief_for_clarifications` function (imported and used in `mailwright.graphs.template_generation_graph`) is successfully mocked using `@patch('mailwright.graphs.template_generation_graph.analyze_brief_for_clarifications', ...)`.
*   The `image_generator_service.generate_image` method (on an instance `image_generator_service` created in `mailwright.graphs.template_generation_graph` and patched via `@patch.object(image_generator_service, 'generate_image', ...)` in the test file after importing the instance) works correctly.

**Current Hypothesis for Failure:**
The methods from the global `mjml_service` instance (defined in `mailwright.graphs.template_generation_graph.py`) might be bound to the LangGraph nodes when `create_graph_builder().compile()` is called within the `compiled_graph_with_memory_saver` fixture. This compilation might occur before the test-specific patches can effectively replace these bound methods for the graph execution context. The `image_generator_service` mock works, which is also an instance, suggesting a subtle difference in how `mjml_service` is being handled or how its methods are referenced.

**Further Debugging Suggestions:**
1.  **Delayed Compilation:** Modify the test/fixture structure so that `graph.compile()` happens *after* the patches are active within the test function's scope. This might involve the fixture yielding the `builder` and `checkpointer`, with the test itself calling `compile`.
2.  **Object Identity Check:** In the test, and within `create_graph_builder` (temporarily, for debugging), print the `id()` of the `mjml_service` instance and its methods to ensure the patched object is the one being used.
3.  **Examine `CompiledStateGraph` internals:** Investigate how LangGraph stores and calls the node callables in the `CompiledStateGraph` to see if the original or mocked function is referenced.