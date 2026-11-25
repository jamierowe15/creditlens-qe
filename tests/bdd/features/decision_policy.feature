@bdd
Feature: Automated credit decision
  As an applicant
  I want an immediate, explained decision on my loan application
  So that I know where I stand and why

  Background:
    Given the CreditLens API is running

  @req:CL-US03 @req:CL-US06 @req:CL-US07 @req:CL-US02
  Scenario Outline: Each persona gets the decision the policy promises
    Given a "<persona>"
    When they submit an application
    Then the decision is "<outcome>"
    And the reasons are "<reasons>"

    Examples:
      | persona                 | outcome  | reasons    |
      | prime borrower          | APPROVED | none       |
      | near-prime borrower     | REFERRED | CS02       |
      | subprime borrower       | DECLINED | CS01       |
      | self-employed owner     | REFERRED | EMP2       |
      | thin-file student       | REFERRED | EMP2       |
      | unemployed applicant    | DECLINED | EMP1       |
      | low-income applicant    | DECLINED | INC1, DTI2 |
      | over-leveraged borrower | DECLINED | DTI1       |

  @req:CL-US04
  Scenario: The new loan payment counts toward debt-to-income
    Given a "prime borrower" with existing monthly debts of 3800 and income of 120000
    When they preview a loan of 10000 over 36 months
    Then the debt-to-income ratio is above 40%
    And the decision is "REFERRED"
    And the reasons are "DTI2"

  @req:CL-US10
  Scenario: Previewing does not save anything
    Given the portfolio total is noted
    When a "prime borrower" previews a decision 3 times
    Then the portfolio total has not changed
