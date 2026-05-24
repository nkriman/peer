# eval-cross-judge-v01 (peer-iaj):
#   - peer.dataset.split.load_split convention

Feature: dataset split convention (.dev.jsonl / .test.jsonl)

  @fast
  Scenario: load_split returns the split file when present
    Given a temp dataset "foo.jsonl" with 10 samples and a sibling "foo.dev.jsonl" with 7 samples
    When I call load_split with base_path "foo.jsonl" and split "dev"
    Then the returned list has length 7

  @fast
  Scenario: load_split falls back when no split exists
    Given a temp dataset "foo.jsonl" with 10 samples and no sibling test file
    When I call load_split with base_path "foo.jsonl" and split "test"
    Then the returned list has length 10

  @fast
  Scenario: unknown split name raises ValueError
    Given a temp dataset "foo.jsonl" with 10 samples
    When I call load_split with base_path "foo.jsonl" and split "production"
    Then ValueError is raised
