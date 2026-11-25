@bdd
Feature: Underwriter review of referred applications
  As an underwriter
  I want to approve or decline applications the engine could not decide
  So that borderline applicants get a human decision that is recorded for audit

  Background:
    Given the CreditLens API is running

  @req:CL-US11 @req:CL-US12
  Scenario Outline: Underwriter resolves a referred application
    Given a "near-prime borrower" has an application that was referred
    When underwriter "<underwriter>" chooses to <action> it with note "<note>"
    Then the application status is "<status>"
    And the audit trail shows "AUTO_DECISION" then "MANUAL_REVIEW" by "<underwriter>"

    Examples:
      | underwriter | action  | note                          | status   |
      | J. Rowe     | approve | Verified two recent pay stubs | APPROVED |
      | A. Singh    | decline | Could not verify income       | DECLINED |

  @req:CL-US11
  Scenario: An automatically approved application cannot be overridden
    Given a "prime borrower" has an application that was approved
    When underwriter "J. Rowe" chooses to decline it with note "Second look"
    Then the review is rejected with "409"
    And the application status is "APPROVED"
