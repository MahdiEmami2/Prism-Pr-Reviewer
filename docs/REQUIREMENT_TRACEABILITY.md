# Requirement traceability

Every requirement from the PRISM specification, mapped to the implementation and to a test
that actually exists. Status meanings are used strictly:

* **PASS** — verified by executing a real test or command in this session; the cited test name
  appears in `pytest --collect-only`.
* **PARTIAL** — implemented, but verification is incomplete; the gap is named.
* **BLOCKED** — an environmental limitation prevented verification; the exact reason is given.
* **NOT IMPLEMENTED** — the functionality does not exist. This is reported, never papered over.

Statuses were **not** assigned by faking tests or checklists. Where no test exists, the row says
so. The full collected inventory is `evidence/H-tests-collected.txt`; the run output is
`evidence/H-pytest.txt`.

---

## 1. Core objective — finding content

| Req | Requirement | Implementation | Evidence / test | Status |
| --- | --- | --- | --- | --- |
| R1.1 | Stable finding identifier | `prism/findings/identity.py::compute_finding_id` | `test_findings.py::test_finding_id_survives_unrelated_line_movement`, `::test_finding_ids_are_stable_across_runs` | PASS |
| R1.2 | Rule identifier and category | `RuleSpec`, `RuleRegistry` | `test_python_rules.py::test_rule_ids_are_unique_and_stable`, `::test_every_registered_rule_has_a_documented_spec` | PASS |
| R1.3 | Five severity levels | `prism/core/types.py::Severity` | `test_api.py::test_rules_endpoint_returns_the_catalogue`, `test_findings.py::test_severity_ranking_and_comparison` | PASS |
| R1.4 | Three confidence levels with documented meaning | `CONFIDENCE_MEANING` | `test_findings.py::test_confidence_meanings_are_documented_for_every_level` | PASS |
| R1.5 | Path and line when reliably available | `FindingFactory.line_if_changed` | `test_python_rules.py::test_finding_locations_point_at_the_changed_line`, `test_findings.py::test_finding_without_a_derivable_line_reports_null_not_a_guess` | PASS |
| R1.6 | Code evidence / diff context | `factory` evidence, `diff/mapping.py` | `test_findings.py::test_finding_to_dict_exposes_every_required_field` (evidence field) | PASS |
| R1.7 | Real-risk explanation | `RuleSpec.description` | `test_findings.py::test_finding_to_dict_exposes_every_required_field` (risk field), `test_reporting.py::test_markdown_report_contains_all_ten_required_sections` | PASS |
| R1.8 | Practical suggested fix | `RuleSpec.remediation` | Same two tests (remediation field / section 7) | PASS |
| R1.9 | Test recommendation | `RuleSpec.test_recommendation` | Same two tests (section 8 present) | PASS |
| R1.10 | Deterministic vs heuristic flag | `FindingClass` | `test_python_rules.py::test_py013_positive_http_call_without_timeout_is_heuristic` | PASS |
| R1.11 | References to rules/documentation | `RuleSpec.documentation` | `test_findings.py::test_finding_to_dict_exposes_every_required_field` | PASS |
| R1.12 | No fabricated findings, results, coverage or sources | no percentage inference path; false-positive notes in `docs/ANALYSIS_RULES.md` | `test_coverage.py::test_coverage_summary_never_claims_a_percentage_from_test_file_counts` | PASS |

## 2. Working rules

| Req | Requirement | Evidence | Status |
| --- | --- | --- | --- |
| R2.1 | Inspect workspace/tools before modifying | `PLAN.md` §0, `evidence/A-environment.txt` (Python 3.12.3, git 2.43.0, pip 24.0, ruff 0.17.1, bandit 1.9.4, no Docker, no Codex) | PASS |
| R2.2 | Preserve existing work | work confined to `/home/user/prism`; the pre-existing `/home/user` files were left untouched (`evidence/A-environment.txt`) | PASS |
| R2.3 | `PLAN.md`, `docs/ACCEPTANCE_CRITERIA.md`, `docs/ARCHITECTURE.md` | all present; `evidence/H-docs.txt` (sha256 of each) | PASS |
| R2.4 | Continue without waiting for approval | Phases A–I executed in one session (`PLAN.md` phase log) | PASS |
| R2.5 | Documented defaults | `PrismConfig`; `test_findings.py::test_config_from_env_parses_and_validates` | PASS |
| R2.6 | No paid API / commercial LLM / cloud needed | `test_external_tools.py::test_external_tools_are_off_by_default` (core runs with no key) | PASS |
| R2.7 | No real tokens/credentials/PII in artefacts | `test_external_tools.py::test_env_example_contains_placeholders_only`, `test_secrets.py::test_finding_evidence_does_not_echo_the_whole_secret`, `evidence/I-zip-grep.txt` | PASS |
| R2.8 | Repository content is untrusted data | `test_python_rules.py::test_analysed_code_cannot_inject_instructions_into_the_report` | PASS |
| R2.9 | Never execute untrusted PR code | `test_python_rules.py::test_analyzers_never_import_or_execute_the_analysed_module` | PASS |
| R2.10 | No publish/push/comment without authorisation | `test_api.py::test_no_endpoint_executes_submitted_code` (route inventory); the GitHub client exposes GET helpers only (code inspection, not test-verified) | **PARTIAL** — no test asserts the absence of a write method |
| R2.11 | Progress tracked in `PLAN.md` | `evidence/H-plan-final.txt` | PASS |
| R2.12 | Recoverable if interrupted | generation script is idempotent; no destructive commands used | PASS |

## 3. Technology stack

| Req | Requirement | Evidence | Status |
| --- | --- | --- | --- |
| R3.1 | Python 3.10+ | `requires-python = ">=3.10"`; CI matrix 3.10/3.11/3.12; executed on 3.12.3 | PASS |
| R3.2 | FastAPI + Pydantic | `prism/api/`; `test_api.py` (21 tests, all passing) | PASS |
| R3.3 | httpx | `prism/github/client.py`; `test_github.py` (27 tests) | PASS |
| R3.4 | `ast` for Python analysis | `test_python_rules.py` (45 tests) | PASS |
| R3.5 | pytest + pytest-cov | `evidence/H-pytest.txt` (259 passed, coverage table) | PASS |
| R3.6 | Ruff lint and format | `evidence/H-ruff.txt` (All checks passed), `evidence/H-ruff-format.txt` (54 files formatted) | PASS |
| R3.7 | Bandit | `evidence/H-bandit.txt` (0 findings at medium or above) | PASS |
| R3.8 | Docker + Compose | `Dockerfile`, `docker-compose.yml`, static checks in `evidence/H-ci-static.txt` | **BLOCKED** — Docker is not installed in this environment, so the image was not built or run here; it is built in the CI `docker` job |
| R3.9 | GitHub Actions | `.github/workflows/ci.yml` (4 jobs) | **PARTIAL** — statically validated only; no workflow run is possible from this environment |
| R3.10 | SQLite / PostgreSQL only if useful | **NOT IMPLEMENTED — deliberate.** The analysis is stateless; persisting untrusted repository content would add risk for no requirement (`docs/ARCHITECTURE.md` §9) | PASS (documented non-choice) |
| R3.11 | Constrained dependencies | `pyproject.toml` upper bounds | PASS |
| R3.12 | Documented supported versions | `README.md` §1, `PLAN.md` §0 | PASS |

## 4. Architecture

| Req | Requirement | Evidence | Status |
| --- | --- | --- | --- |
| R4.1–R4.10 | Module separation exactly as enumerated (api, core, github, diff, analyzers, engine, findings, reporting, coverage, tests, docs) | directory listing in this session; every module imported by the passing suite | PASS |
| R4.11 | No circular imports | one-way dependency direction; the whole package imports cleanly in every test run and `ruff` reports no import errors | PASS |

## 5. Review inputs

| Req | Requirement | Test | Status |
| --- | --- | --- | --- |
| R5.1 | Local diff file | `test_diff_parser.py::test_added_file_is_parsed_with_new_side_line_numbers` | PASS |
| R5.2 | Diff from a local Git repository | none | **PARTIAL** — `parse_local_git_diff` is implemented (fixed argv, `shell=False`, timeout) and reviewed, but no test exercises it; only the file-based path was run |
| R5.3 | GitHub PR by owner/repo/number | `test_github.py::test_end_to_end_pull_request_review_uses_mocked_transport` | PASS |
| R5.4 | PR metadata, files, patches | `test_github.py::test_pull_request_metadata_is_parsed` | PASS |
| R5.5 | Public PRs work without a token | `test_github.py::test_token_is_sent_when_configured_and_absent_when_not` | PASS |
| R5.6 | Optional token via environment | `test_secrets.py::test_config_reads_token_from_environment` | PASS |
| R5.7 | Read-only permissions | `test_github.py::test_end_to_end_pull_request_review_uses_mocked_transport` (GET-only throughout) | PASS |
| R5.8 | Pagination | `test_github.py::test_pagination_follows_the_link_header`, `::test_pagination_stops_at_the_configured_page_cap` | PASS |
| R5.9 | Rate limits | `test_github.py::test_rate_limit_error_carries_the_reset_instant_and_no_token`, `::test_retry_after_header_is_surfaced` | PASS |
| R5.10 | Timeouts | none for the HTTP path | **PARTIAL** — `http_timeout_seconds` is wired into every request and validated in config, but no test asserts a request timeout |
| R5.11 | Missing patches / binary files | `test_github.py::test_file_entry_without_a_patch_becomes_a_skipped_record`, `::test_binary_status_is_recorded_as_binary` | PASS |
| R5.12 | Deleted files | `test_github.py::test_deleted_file_entry_is_recorded_and_not_analysed`, `test_diff_parser.py::test_deleted_file_is_recorded_and_not_analyzable` | PASS |
| R5.13 | Large diffs / API errors | `test_github.py::test_oversized_json_response_is_rejected_before_parsing`, `::test_unauthorized_and_not_found_map_to_typed_errors`, `::test_non_json_response_is_reported_as_a_github_error` | PASS |
| R5.14 | Skipped files and incomplete analysis reported | `test_reporting.py::test_markdown_lists_limitations_and_scoped_skips` | PASS |
| R5.15 | Never log auth headers or tokens | `test_secrets.py::test_logging_filter_scrubs_secrets_from_messages_and_arguments` | PASS |
| R5.16 | Size, file, time and response limits with explicit errors | `test_diff_parser.py::test_oversized_diff_raises_with_the_limit_in_the_details`, `::test_file_count_limit_truncates_and_records_it`, `test_api.py::test_oversized_body_is_rejected_with_413` | PASS |

## 6. Analysis engine

| Req | Rule / capability | Test | Status |
| --- | --- | --- | --- |
| R6.1 | Plugin registry, stable IDs | `test_python_rules.py::test_rule_ids_are_unique_and_stable`, `test_external_tools.py::test_registry_excludes_external_rules_unless_enabled` | PASS |
| R6.2 | PY001 mutable default | `::test_py001_positive_mutable_default_list_argument`, `::test_py001_negative_none_default_then_build_inside`, `::test_py001_boundary_kwonly_default_and_dict_default` | PASS |
| R6.3 | PY002 bare except | `::test_py002_positive_bare_except`, `::test_py002_negative_specific_exception` | PASS |
| R6.4 | PY003 swallowed exception | `::test_py003_positive_except_pass`, `::test_py003_negative_except_with_action`, `::test_py003_negative_comment_inside_except_block` | PASS |
| R6.5 | PY004 shell=True | `::test_py004_positive_shell_true`, `::test_py004_negative_shell_false_literal`, `::test_py004_negative_argument_list_without_shell` | PASS |
| R6.6 | PY005/PY006 dynamic exec and deserialisation | `::test_py005_positive_eval_and_exec_and_compile`, `::test_py005_negative_literal_eval_and_re_compile`, `::test_py006_positive_pickle_loads`, `::test_py006_negative_json_loads` | PASS |
| R6.7 | PY007/PY008 unsafe YAML and shell helpers | `::test_py007_positive_yaml_load_without_safe_loader`, `::test_py007_negative_yaml_safe_load_and_explicit_safe_loader`, `::test_py008_positive_os_system`, `::test_py008_negative_subprocess_argument_list` | PASS |
| R6.8 | PY009/PY010/PY011 temp file, weak hash, TLS | `::test_py009_positive_mktemp`, `::test_py009_negative_named_temporary_file`, `::test_py010_positive_md5`, `::test_py010_negative_sha256_and_opt_out`, `::test_py011_positive_tls_verification_disabled`, `::test_py011_negative_verification_left_on` | PASS |
| R6.9 | PY012 control flow | `::test_py012_positive_statement_after_return`, `::test_py012_negative_all_branches_return` | PASS |
| R6.10 | PY013 missing timeout (heuristic) | `::test_py013_positive_http_call_without_timeout_is_heuristic`, `::test_py013_negative_explicit_timeout_present` | PASS |
| R6.11 | PY014 syntax error; PY015 assert | `::test_py014_positive_syntax_error_in_added_file`, `::test_py014_negative_valid_file_produces_no_syntax_finding`, `::test_py015_positive_assert_used_for_validation`, `::test_py015_negative_explicit_raise` | PASS |
| R6.12 | SEC001 credentials with placeholder safeguards | `test_secrets.py::test_sec001_positive_literal_password`, `::test_sec001_negative_obvious_placeholders_are_not_reported`, `::test_sec001_negative_environment_lookup`, `::test_sec001_boundary_short_value_is_ignored`, `::test_sec001_reports_in_non_python_files_too`, `::test_is_placeholder_is_a_first_class_guarantee` | PASS |
| R6.13 | SEC002 / SEC003 | `test_secrets.py::test_sec002_positive_private_key_header`, `::test_sec002_negative_public_key_and_certificate_headers`, `::test_sec003_positive_high_entropy_literal_next_to_secret_name`, `::test_sec003_negative_ordinary_text_and_hashes_are_not_flagged`, `::test_entropy_helper_boundaries` | PASS |
| R6.14 | TST001 changed source without test change (heuristic) | `test_coverage.py::test_source_change_without_test_change_emits_one_heuristic_finding`, `::test_no_finding_when_a_test_file_changed_too`, `::test_no_finding_when_only_tests_changed`, `::test_long_source_list_is_truncated_and_flagged` | PASS |
| R6.15 | No keyword-only flagging | `test_python_rules.py::test_no_finding_is_emitted_for_purely_clean_code`, `::test_added_file_paths_are_preserved` | PASS |
| R6.16 | Parse safely; syntax errors caught; line numbers preserved | `::test_py014_positive_syntax_error_in_added_file`, `::test_finding_locations_point_at_the_changed_line` | PASS |
| R6.17 | Heuristics labelled, never claimed as proof | `::test_py013_positive_http_call_without_timeout_is_heuristic`, `test_coverage.py::test_source_change_without_test_change_emits_one_heuristic_finding` | PASS |
| R6.18 | Partial diffs and deleted lines handled | `test_diff_parser.py::test_added_line_fragment_is_dedented_and_keeps_the_line_map`, `::test_added_line_fragment_is_none_when_the_diff_only_removes_lines`, `test_python_rules.py::test_fragment_view_is_reported_in_scope_diagnostics`, `::test_pre_existing_code_on_unchanged_lines_is_out_of_scope`, `::test_syntax_error_in_a_modified_file_is_not_reported_as_a_defect` | PASS |
| R6.19 | Optional Ruff/Bandit with availability and return-code checks | `test_external_tools.py::test_ruff_adapter_reports_findings_with_a_real_exit_code`, `::test_bandit_adapter_maps_severity_and_reports_its_exit_code`, `::test_missing_executable_is_reported_as_unavailable_not_an_error`, `::test_unexpected_exit_code_is_reported_as_failure`, `::test_unparseable_tool_output_is_reported_as_failure`, `::test_tool_timeout_is_reported_as_timeout`, `::test_tool_reports_are_rendered_in_the_markdown_report` | PASS |

## 7. Finding quality

| Req | Requirement | Test | Status |
| --- | --- | --- | --- |
| R7.1 | Normalisation + dedup layer | `test_findings.py::test_deduplicate_collapses_identical_ids_and_logs_it`, `::test_deduplicate_output_is_deterministically_ordered` | PASS |
| R7.2 | Identity from rule, path, symbol, signature | `test_findings.py::test_finding_id_differs_across_rules_and_signatures`, `::test_finding_id_differs_for_different_files`, `::test_discriminator_separates_two_similar_sites` | PASS |
| R7.3 | Not line-number dependent | `::test_finding_id_survives_unrelated_line_movement` | PASS |
| R7.4 | Distinct problems in one file not merged | `::test_deduplicate_keeps_distinct_problems_in_the_same_file` | PASS |
| R7.5 | Severity and confidence separate, mapping documented | `::test_severity_and_confidence_are_independent_dimensions`, `::test_confidence_meanings_are_documented_for_every_level` | PASS |
| R7.6 | Never inflated severity | `test_python_rules.py::test_every_registered_rule_has_a_documented_spec` (every default comes from a declared spec), `test_external_tools.py::test_external_specs_declare_fixed_severities` | PASS |
| R7.7 | Configurable thresholds and exclusions, safe defaults | `test_findings.py::test_default_configuration_suppresses_nothing`, `::test_minimum_severity_filters_and_records_the_suppression`, `::test_rule_exclusion_removes_exactly_that_rule`, `::test_severity_override_is_applied_and_recorded`, `::test_invalid_minimum_severity_raises_config_error` | PASS |
| R7.8 | Suppressions recorded with the policy | `test_reporting.py::test_suppressed_findings_are_visible_in_the_json_report`, `test_api.py::test_severity_policy_is_applied_per_request` | PASS |

## 8. Test coverage and missing tests

| Req | Requirement | Test | Status |
| --- | --- | --- | --- |
| R8.1 | Configurable test-file detection | `test_coverage.py::test_test_path_conventions_are_recognised`, `::test_custom_test_conventions_are_honoured`, `::test_conftest_is_a_test_file_by_default`, `::test_non_test_paths_are_not_treated_as_tests` | PASS |
| R8.2 | Test-related changes identified | `test_coverage.py::test_source_change_without_test_change_emits_one_heuristic_finding` | PASS |
| R8.3 | Cobertura XML accepted | `test_coverage.py::test_cobertura_is_parsed_with_line_level_detail` | PASS |
| R8.4 | Coverage associated only where the report supports it | `::test_uncovered_changed_line_produces_tst002`, `::test_coverage_is_only_matched_by_exact_path`, `::test_changed_file_missing_from_the_report_produces_informational_tst003` | PASS |
| R8.5 | Missing/stale/unavailable coverage explained | `::test_missing_coverage_file_yields_unavailable_not_an_exception`, `::test_empty_coverage_report_is_unavailable`, `::test_malformed_coverage_xml_reports_unavailable_with_a_reason`, `::test_wrong_root_element_is_reported`, `::test_review_without_coverage_says_so_in_the_limitations`, `::test_review_with_coverage_notes_the_staleness_caveat` | PASS |
| R8.6 | Never infer a percentage from test-file counts | `::test_coverage_summary_never_claims_a_percentage_from_test_file_counts` | PASS |
| R8.7 | Missing tests as suggestions/heuristics only | `::test_source_change_without_test_change_emits_one_heuristic_finding`, `::test_no_coverage_report_means_no_coverage_findings` | PASS |

## 9. Reporting

| Req | Requirement | Test | Status |
| --- | --- | --- | --- |
| R9.1 | Markdown report | `test_reporting.py::test_markdown_report_contains_all_ten_required_sections` | PASS |
| R9.2 | JSON report | `::test_json_report_matches_the_documented_top_level_schema`, `::test_json_round_trips_and_keeps_confidence_meaning` | PASS |
| R9.3 | Ten sections, always present | `::test_empty_review_still_renders_all_sections`, `::test_report_rule_catalogue_lists_every_registered_rule` | PASS |
| R9.4 | Untrusted text escaped | `::test_hostile_diff_content_cannot_corrupt_report_structure`, `::test_hostile_filename_does_not_break_the_table`, `::test_hostile_path_in_a_non_table_line_is_still_neutralised`, `::test_hostile_pr_metadata_cannot_inject_markup`, `::test_code_block_cannot_be_broken_out_of`, `::test_escape_markdown_escapes_structural_characters`, `::test_escape_table_cell_neutralises_pipes_and_newlines`, `::test_safe_text_neutralises_html_and_control_characters`, `::test_inline_code_replaces_backticks` | PASS |
| R9.5 | Never claim a report was posted | `::test_report_states_that_nothing_is_published` | PASS |
| (bonus) | Deterministic output | `::test_json_report_is_byte_identical_across_runs`, `::test_json_report_has_no_timestamp_unless_explicitly_enabled`, `::test_json_report_can_include_a_timestamp_when_asked` | PASS |

## 10. FastAPI

| Req | Requirement | Test | Status |
| --- | --- | --- | --- |
| R10.1 | `GET /health` | `test_api.py::test_health_endpoint_reports_capabilities_without_secrets` | PASS |
| R10.2 | `GET /version` | `::test_version_endpoint_lists_rules_and_limitations` | PASS |
| R10.3 | `POST /api/v1/reviews/diff` | `::test_diff_review_endpoint_returns_findings` | PASS |
| R10.4 | `POST /api/v1/reviews/github` | `::test_github_endpoint_uses_an_injected_mock_transport` | PASS |
| R10.5 | Pydantic models | `::test_github_endpoint_accepts_coordinates_only_no_url_field`, `test_findings.py::test_unknown_severity_is_rejected_by_deserialisation_boundary` | PASS |
| R10.6 | Validation and size limits | `::test_diff_review_rejects_empty_diff`, `::test_diff_review_rejects_non_diff_input_with_a_useful_code`, `::test_oversized_body_is_rejected_with_413`, `::test_unknown_fields_are_rejected`, `::test_invalid_rule_identifier_is_rejected`, `::test_body_size_limit_is_configurable_and_enforced` | PASS |
| R10.7 | Consistent error envelope | `::test_error_envelope_is_consistent` | PASS |
| R10.8 | Secret-free logging | `test_secrets.py::test_logging_filter_scrubs_secrets_from_messages_and_arguments` | PASS |
| R10.9 | API documentation | `::test_openapi_document_is_served_and_describes_all_routes` | PASS |
| R10.10 | Timeouts and resource limits | `::test_response_includes_a_process_time_header`, `docker-compose.yml` limits | **PARTIAL** — limits are configured and the timing header is tested; the container-level limits were never executed (no Docker) |
| R10.11 | No paths or environment values in responses | `::test_no_response_leaks_filesystem_paths_or_environment_values` | PASS |
| R10.12 | No code-execution endpoint | `::test_no_endpoint_executes_submitted_code` | PASS |
| R10.13 | GitHub owner/repo validation | `::test_github_endpoint_rejects_a_non_github_owner` | PASS |

## 11. Security

| Req | Requirement | Test / evidence | Status |
| --- | --- | --- | --- |
| R11.1 | Threat-model review | `docs/THREAT_MODEL.md` (T1–T13, residual R1–R7), `evidence/H-docs.txt` | PASS |
| R11.2 | Untrusted repository content | `test_python_rules.py::test_analysed_code_cannot_inject_instructions_into_the_report` | PASS |
| R11.3 | Prompt injection if AI is added | no provider ships; contract documented in `docs/ANALYSIS_RULES.md` | **PARTIAL** — the contract is documented and the extension is inert, but no test exercises the validation or merge helpers (no provider exists to drive them) |
| R11.4 | Token protection / least privilege | `test_secrets.py::test_config_never_exposes_the_token_value`, `test_github.py::test_token_is_sent_when_configured_and_absent_when_not`, `::test_rate_limit_error_carries_the_reset_instant_and_no_token` | PASS |
| R11.5 | SSRF / arbitrary URL | `test_github.py::test_unsupported_urls_are_rejected`, `::test_api_base_must_be_https_and_allow_listed`, `::test_path_segments_cannot_smuggle_traversal_into_an_api_url`, `::test_bad_owners_are_rejected`, `::test_bad_repo_names_are_rejected`, `::test_bad_pull_numbers_are_rejected`, `test_api.py::test_github_endpoint_accepts_coordinates_only_no_url_field` | PASS |
| R11.6 | Path traversal | `test_findings.py::test_path_normalisation_handles_prefixes_and_traversal`, `test_api.py::test_path_traversal_shaped_diff_path_is_handled_without_touching_disk` | PASS |
| R11.7 | Malicious Markdown / report injection | `test_reporting.py` escaping block (see R9.4) | PASS |
| R11.8 | DoS via oversized or pathological input | `test_diff_parser.py::test_oversized_diff_raises_with_the_limit_in_the_details`, `::test_oversized_patch_is_skipped_rather_than_partially_analysed`, `::test_nul_bytes_and_control_characters_do_not_crash_the_parser`, `::test_very_long_single_line_is_processed`, `test_coverage.py::test_oversized_coverage_report_is_rejected`, `test_api.py::test_oversized_body_is_rejected_with_413` | PASS |
| R11.9 | Unsafe subprocess execution | tool failure modes are tested; `shell=False` with a fixed argv is by code inspection | **PARTIAL** — no test asserts the absence of a shell string |
| R11.10 | Dependency vulnerabilities | Bandit SAST run (`evidence/H-bandit.txt`) | **PARTIAL** — no dependency-CVE scanner is wired up; documented as a gap in `docs/THREAT_MODEL.md` T9 |
| R11.11 | Sensitive-data leakage | `test_secrets.py::test_finding_evidence_does_not_echo_the_whole_secret`, `::test_redact_removes_credential_shapes`, `::test_safe_env_names_reports_names_only`, `evidence/I-zip-grep.txt` | PASS |
| R11.12 | Safe GitHub Actions permissions | `evidence/H-ci-static.txt`: unprivileged trigger (0 privileged-trigger uses), no `write-all`, top-level `contents: read`, 3× `persist-credentials: false` | PASS (static) |
| R11.13 | Only supported GitHub URL formats | `test_github.py::test_valid_pull_request_url_parses`, `::test_unsupported_urls_are_rejected`, `::test_repo_name_with_git_suffix_is_normalised` | PASS |
| R11.14 | Never `eval` / execute analysed code | `test_python_rules.py::test_analyzers_never_import_or_execute_the_analysed_module` | PASS |
| R11.15 | Secure defaults, residual risks documented | `docs/THREAT_MODEL.md` §4, `docs/DATA_PRIVACY.md` | PASS |

## 12. Optional AI extension

| Req | Requirement | Status |
| --- | --- | --- |
| R12.1 | Core works without an LLM | PASS — `test_external_tools.py::test_external_tools_are_off_by_default`; nothing in the analysis path imports a provider |
| R12.2 | Disabled by default, no API key required | PASS — `enable_llm_extension` defaults to false; no key is read or documented |
| R12.3 | Model findings labelled heuristic | **PARTIAL** — enforced in code (`merge_llm_findings` unions and downgrades) but untested, because no provider ships to produce a finding |
| R12.4 | Strict schema validation, paths re-checked against the diff | **PARTIAL** — helpers exist and are reviewed; untested for the same reason |
| R12.5 | No source/secret leakage by default | PASS — disabled by default plus the redaction layer (`test_secrets.py` redaction block) |
| R12.6 | Instructions in analysed code never trusted | PASS — there is no instruction channel (`test_python_rules.py::test_analysed_code_cannot_inject_instructions_into_the_report`) |
| R12.7 | Deterministic fallback with no provider | **PARTIAL** — `NullProvider` exists and returns nothing; no test exercises it |
| R12.8 | Never suppress deterministic findings via an LLM | **PARTIAL** — merge is a union in code; untested |
| R12.9 | No fabricated AI evaluation claims | PASS — none made; `README.md` §15 states no evaluation was performed |

## 13. Testing

| Req | Requirement | Evidence | Status |
| --- | --- | --- | --- |
| R13.1 | Tests for each rule, positive and negative | `test_python_rules.py` (45), `test_secrets.py` (19) | PASS |
| R13.2 | AST parsing errors | `test_python_rules.py::test_py014_positive_syntax_error_in_added_file`, `::test_fragment_view_is_reported_in_scope_diagnostics` | PASS |
| R13.3 | Diff parsing and line mapping | `test_diff_parser.py` (25) | PASS |
| R13.4 | Added/modified/deleted/renamed/binary | `test_diff_parser.py::test_added_file_is_parsed_with_new_side_line_numbers`, `::test_modified_file_maps_lines_across_multiple_hunks`, `::test_deleted_file_is_recorded_and_not_analyzable`, `::test_rename_is_parsed_with_both_paths`, `::test_binary_file_is_skipped_with_a_reason_not_an_error` | PASS |
| R13.5 | Duplicate findings and stable IDs | `test_findings.py` dedupe and ID block | PASS |
| R13.6 | Severity/confidence validation | `test_findings.py::test_severity_and_confidence_are_independent_dimensions`, `::test_severity_ranking_and_comparison` | PASS |
| R13.7 | Markdown escaping, JSON serialisation | `test_reporting.py` (24) | PASS |
| R13.8 | GitHub pagination and rate limits | `test_github.py` (27) | PASS |
| R13.9 | API validation and errors | `test_api.py` (21) | PASS |
| R13.10 | Missing coverage reports | `test_coverage.py` (24) | PASS |
| R13.11 | Malformed/oversized inputs | `test_diff_parser.py`, `test_coverage.py`, `test_api.py` limit tests | PASS |
| R13.12 | Secret redaction | `test_secrets.py` redaction block | PASS |
| R13.13 | URL and path validation | `test_github.py`, `test_findings.py` validation blocks | PASS |
| R13.14 | Mocked HTTP, no live token or internet | `httpx.MockTransport` in `test_api.py`/`test_github.py`; autouse socket guard in `tests/conftest.py::_block_network`; the 2 live tests are skipped unless `PRISM_RUN_INTEGRATION=1` | PASS |
| R13.15 | Regression test per bug found | `docs/TESTING.md` §5 (11 named regressions, all present in the collected inventory) | PASS |
| R13.16 | Run pytest, Ruff, security; fix root causes | `evidence/H-pytest.txt`, `evidence/H-ruff.txt`, `evidence/H-ruff-format.txt`, `evidence/H-bandit.txt` | PASS |
| R13.17 | State when a tool cannot run and why | Docker and Codex CLI recorded as unavailable with reasons (`evidence/A-environment.txt`) | PASS |

## 14. CI and containerisation

| Req | Requirement | Status |
| --- | --- | --- |
| R14.1 | Dockerfile | **BLOCKED** — not executed (Docker absent); statically checked (non-root `USER`, no compiler in the runtime stage, `HEALTHCHECK` present) |
| R14.2 | Docker Compose | **BLOCKED** — same reason; hardening verified statically (read-only root, `noexec` tmpfs, `no-new-privileges`, `cap_drop`, non-root user, CPU and memory caps) |
| R14.3 / R14.4 | `.dockerignore`, `.gitignore` | PASS — both present and inside the archive |
| R14.5 | `.env.example` with placeholders only | PASS — `test_external_tools.py::test_env_example_contains_placeholders_only` |
| R14.6 | CI workflow for lint and tests | PASS (static) — 4 jobs: quality, security, docker, plus the push trigger |
| R14.7 | Minimal Actions permissions | PASS (static) — `contents: read` top level; no `write-all` |
| R14.8 | Dependency and security checks where practical | **PARTIAL** — Bandit runs; no dependency-CVE scanner |
| R14.9 | PR code treated as untrusted | PASS (static) — unprivileged trigger, no step executes analysed code |
| R14.10 | No write permissions unless justified | PASS (static) |

## 15. Documentation

| Req | Requirement | File | Status |
| --- | --- | --- | --- |
| R15.1–R15.5 | README with overview, architecture, install (PowerShell + Linux/macOS), both usage modes, API examples, configuration, rule catalog, sample report, testing, Docker, security/privacy, limitations, roadmap, contribution | `README.md` (17 sections) | PASS |
| R15.6 | German summary for an IT Ausbildung portfolio | `README.md` "Projektzusammenfassung (Deutsch)" | PASS |
| R15.7 | LICENSE | `LICENSE` (MIT — stated assumption in `PLAN.md` §0) | PASS |
| R15.8 | CONTRIBUTING, SECURITY, CHANGELOG | all present | PASS |
| R15.9 | ACCEPTANCE_CRITERIA, ARCHITECTURE, THREAT_MODEL, ANALYSIS_RULES, TESTING, DATA_PRIVACY | all present, plus SPEC and this matrix | PASS |
| R15.10 | No certifications, deployments, customers, performance or security guarantees claimed | verified while writing; capability sentences name a test | PASS |

## 16. Demonstration

| Req | Requirement | Test / evidence | Status |
| --- | --- | --- | --- |
| R16.1 | Sample project with planted problems and a test file | `samples/sample_project/`; `test_sample_project.py::test_risky_sample_triggers_the_expected_rule_set` | PASS |
| R16.2 | Sample diff saved | `examples/sample_diff.patch`; `::test_committed_example_reports_exist_and_are_labelled` | PASS |
| R16.3 | Markdown + JSON reports saved | `examples/sample_report.md`, `examples/sample_report.json` (generated by a real run: 22 findings across 16 rules) | PASS |
| R16.4 | Clean code that does not trigger the rules | `samples/sample_project/clean_module.py`; `::test_clean_sample_produces_no_findings` | PASS |
| R16.5 | Labelled as demonstration data | `samples/sample_project/README.md`; `::test_sample_review_is_labelled_as_demonstration_data`, `::test_placeholder_configuration_produces_no_credential_findings` | PASS |

## 17. Development workflow

| Req | Phase | Status |
| --- | --- | --- |
| R17.1 | A — inspect and plan | PASS (`PLAN.md` §0–1, `evidence/A-environment.txt`) |
| R17.2–R17.6 | B, C, D, E, F | PASS — each phase recorded in the `PLAN.md` phase table |
| R17.7 | G — documentation, CI, Docker config | PASS for documentation and CI config; Docker **execution BLOCKED** |
| R17.8 | H — tests, lint, security, self-review | PASS (`evidence/H-*`) |
| R17.9 | I — fix, package, honest report | PASS |
| R17.10 | Do not stop at the plan | PASS — full implementation delivered |
| R17.11 | Codex CLI independent review if installed | **BLOCKED** — Codex CLI is not installed; a documented self-review was performed and no extra tool was installed for it |

## 18. Release and ZIP

| Req | Requirement | Evidence | Status |
| --- | --- | --- | --- |
| R18.1 | `dist/PRISM.zip` exists | `evidence/I-zip.txt` | PASS |
| R18.2 | `unzip -t` passes | `evidence/I-zip.txt` ("No errors detected") | PASS |
| R18.3 | Source, tests and documentation included | `unzip -l` listing in `evidence/I-zip.txt` | PASS |
| R18.4 | No secrets or local environment files | `evidence/I-zip-grep.txt`: 0 entries for `.env`, `.git/`, `__pycache__`, `.pyc`, `venv/`, `.coverage`; every secret-shaped literal classified as a deliberate fixture | PASS |
| R18.5 | README and installation match the implementation | documented flags and endpoints are the implemented ones | PASS |
| R18.6 | Final test results accurately recorded | test count and coverage quoted from `evidence/H-pytest.txt` in the reply | PASS |
| R18.7 | A valid ZIP does not prove the app works; report separately | test, lint, security and build results are reported as separate items | PASS |

## 19. Completion report

| Req | Requirement | Status |
| --- | --- | --- |
| R19.1–R19.3 | Implemented items, directory, modes, rules | PASS — in the reply |
| R19.4 | Test count and actual results | PASS — real numbers from this run |
| R19.5 | Lint and security results | PASS |
| R19.6 | Docker status | PASS — reported BLOCKED with the reason |
| R19.7 | Known limitations, including the PARTIAL rows above | PASS |
| R19.8 | Exact ZIP path and size | PASS |
| R19.9 | Commands to run locally | PASS |
| R19.10 | Remaining tasks | PASS |
| R19.11 | Never claim a command passed unless executed | PASS — unexecuted items are marked BLOCKED or PARTIAL |
