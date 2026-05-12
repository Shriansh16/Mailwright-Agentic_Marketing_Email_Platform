# Sprint 2: Error Handling Integration Test Plan

**Overall Goal:**
Enhance `tests/integration/test_template_generation_graph.py` with new test cases that specifically target error conditions within each critical node of the `template_generation_graph`. These tests will ensure that errors are correctly reported in the `GraphState` (`error_message`, `last_operation_status`) and that the graph transitions to the `END` state when errors are unrecoverable by the current logic.

**General Test Structure:**
Each new error integration test will typically follow this pattern:
1.  **Setup:**
    *   Define an initial `GraphState` (often using `sample_user_brief_input` fixture).
    *   Configure a `thread_id`.
    *   Use a `MemorySaver` checkpointer for simplicity, unless the test specifically involves checkpointer or `StoreV0Node` database errors.
    *   Compile the graph: `builder = create_graph_builder(); graph = builder.compile(checkpointer=checkpointer)`.
2.  **Mocking:**
    *   Use `@patch` from `unittest.mock` to target the function/method call within the graph node that is expected to cause an error.
    *   The mock should be configured to either:
        *   Raise an exception.
        *   Return a specific error object or status dict that the node logic is designed to handle (e.g., `BriefAnalysisResult(status="ERROR", ...)`).
3.  **Execution:**
    *   Invoke the graph using `await graph.ainvoke(initial_input, config=config)`. For some tests, it might be useful to `interrupt_after` a specific node or `interrupt_before=[END]` to inspect the state at a particular point.
4.  **Assertions:**
    *   Verify the `final_state_data` is not `None`.
    *   Construct `GraphState(**final_state_data)`.
    *   Assert that `final_state.error_message` contains the expected error description.
    *   Assert that `final_state.last_operation_status` reflects the specific error status for that node or a generic "ERROR".
    *   Assert that the graph has indeed reached the `END` state. This can be implicitly checked if `ainvoke` completes and the final state is retrieved, and the conditional edges route to `END` upon error. We can also check `graph.get_state(config).next` to see if it's empty after an error leads to `END`.

---

**Planned Test Cases:**

**I. `LG_BriefAnalyzer` Node Errors:**

1.  **`test_graph_error_brief_analyzer_missing_data`**:
    *   **Scenario**: `state.user_brief_data` is `None`.
    *   **Mock**: No service mocking needed; the node's internal check should catch this.
    *   **Initial State**: `user_brief_data=None`.
    *   **Assertions**: `error_message == "User brief data is missing."`, `last_operation_status == "ERROR"`. Graph reaches `END`.
2.  **`test_graph_error_brief_analyzer_invalid_data`**:
    *   **Scenario**: `state.user_brief_data` fails Pydantic validation.
    *   **Mock**: No service mocking needed.
    *   **Initial State**: `user_brief_data={"invalid_field": "xyz"}`.
    *   **Assertions**: `error_message` contains "Invalid user brief data format", `last_operation_status == "ERROR"`. Graph reaches `END`.
    *   *(Note: `test_graph_flow_brief_analyzer_error` already covers the case where the `analyze_brief_for_clarifications` service itself returns an error status. This is distinct.)*

**II. `LG_ImageGeneration` Node Errors:**

1.  **`test_graph_error_image_generation_service_exception`**:
    *   **Scenario**: `image_generator_service.generate_image` raises an unexpected exception.
    *   **Mock**: Patch `mailwright.graphs.template_generation_graph.image_generator_service.generate_image` to `side_effect=Exception("DALL-E unavailable")`.
    *   **Initial State**: Valid `user_brief_data` and `image_prompts=["prompt1"]`.
    *   **Assertions**: `error_message` contains "Exception for prompt 'prompt1': DALL-E unavailable", `last_operation_status == "ERROR_IMAGE_GENERATION"`. Graph proceeds (as per current node logic which accumulates errors).
2.  **`test_graph_error_image_generation_all_prompts_fail`**:
    *   **Scenario**: `image_generator_service.generate_image` returns `None` for all image prompts.
    *   **Mock**: Patch `mailwright.graphs.template_generation_graph.image_generator_service.generate_image` to `return_value=None`.
    *   **Initial State**: `image_prompts=["prompt1", "prompt2"]`.
    *   **Assertions**: `error_message` contains "Failed to retrieve URL for prompt 'prompt1'; Failed to retrieve URL for prompt 'prompt2'", `generated_image_urls == []`, `last_operation_status == "ERROR_IMAGE_GENERATION"`.

**III. `LG_MJMLGeneration` Node Errors (via `mjml_service.generate_mjml_node`):**

1.  **`test_graph_error_mjml_generation_service_exception`**:
    *   **Scenario**: The `mjml_service.generate_mjml_node` (called as the graph node) itself raises an exception (e.g., simulating an LLM API failure within the service method).
    *   **Mock**: Patch `mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node` (the method instance on the global `mjml_service` used by the graph) to `side_effect=Exception("MJML LLM failed")`.
    *   **Initial State**: Path that would lead to MJML generation (e.g., after BRIEF_OK and successful image generation mock).
    *   **Assertions**: The error should be caught by the `mjml_service.generate_mjml_node`'s internal error handling, which should then set `state.error_message` and `state.last_operation_status` appropriately (e.g., `ERROR_MJML_GENERATION`). The graph should then proceed to validation, which should detect this error state and route to `END`.
2.  **`test_graph_error_mjml_generation_service_returns_error_status`**:
    *   **Scenario**: `mjml_service.generate_mjml_node` returns a dict indicating an error.
    *   **Mock**: Patch `mailwright.graphs.template_generation_graph.mjml_service.generate_mjml_node` to return `{"last_operation_status": "ERROR_MJML_GENERATION", "error_message": "Bad MJML content generated"}`.
    *   **Assertions**: `error_message` and `last_operation_status` are as returned by the mock. Graph proceeds to validation, which then routes to `END`.

**IV. `LG_MJMLValidateCompile` Node Errors (via `mjml_service.validate_and_compile_mjml_node`):**

1.  **`test_graph_error_mjml_validation_service_exception`**:
    *   **Scenario**: `mjml_service.validate_and_compile_mjml_node` raises an unexpected exception (e.g., `mjml` CLI not found or crashes).
    *   **Mock**: Patch `mailwright.graphs.template_generation_graph.mjml_service.validate_and_compile_mjml_node` to `side_effect=Exception("MJML CLI error")`.
    *   **Assertions**: Similar to MJML generation, the service node's internal error handling should set `state.error_message` and `state.last_operation_status`. The graph should then route to `END` via `should_store_or_end_after_validation`.
2.  **`test_graph_error_mjml_validation_invalid_mjml`**:
    *   **Scenario**: `mjml_service.validate_and_compile_mjml_node` processes invalid MJML and returns the appropriate error status.
    *   **Mock**: Patch `mailwright.graphs.template_generation_graph.mjml_service.validate_and_compile_mjml_node` to return `{"mjml_validation_status": "INVALID", "error_message": "Invalid MJML syntax", "last_operation_status": "ERROR_MJML_VALIDATION", "compiled_html": None}`.
    *   **Assertions**: `mjml_validation_status == "INVALID"`, `error_message` set, `last_operation_status` set. Graph routes to `END`.

**V. `LG_StoreV0` Node Errors:**

1.  **`test_graph_error_store_v0_missing_data`**:
    *   **Scenario**: Graph reaches `store_v0_node`, but `state.current_mjml` is `None`.
    *   **Setup**: Mock the preceding `mjml_service.validate_and_compile_mjml_node` to return a "VALID" status but with `current_mjml=None` and `compiled_html="some html"` (or vice-versa for `compiled_html`).
    *   **Assertions**: `error_message == "MJML source or compiled HTML missing for storing version."`, `last_operation_status == "ERROR_STORING_VERSION"`. Graph reaches `END`.
2.  **`test_graph_error_store_v0_db_exception`**:
    *   **Scenario**: `create_template_version` (called within `store_v0_node`) raises a database exception.
    *   **Mock**: Patch `mailwright.graphs.template_generation_graph.create_template_version` to `side_effect=Exception("Simulated DB unique constraint violation")`.
    *   **Checkpointer**: Use `active_postgres_checkpointer` because `StoreV0Node` interacts with the DB.
    *   **Assertions**: `error_message` contains "Database error storing version v0", `last_operation_status == "ERROR_STORING_VERSION"`. Graph reaches `END`.

---
This plan will guide the implementation of the new integration tests. 