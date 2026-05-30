# TraceQual Future Work

## Confidence rule redesign (unvalidated)

Potential redesign inputs include decision-type (accepted/modified/rejected/deferred/unclear), reasoning length or specificity, hedging-language presence, and decision-reasoning agreement features. Any redesign must be validated against multiple independent fixtures and must not be tuned on the single existing synthetic fixture, to avoid overfitting to an n-of-1 test case. No redesign has been validated; the v1 confidence derivation rule remains in force.

## ChatGPT export support

Add optional support for ChatGPT account export JSON by traversing the conversation tree from the root through child links, extracting speaker from `author.role`, joining text from `content.parts`, and filtering out the hidden system node and null-message root. This is deliberately deferred from v1 because ChatGPT export schemas have changed historically, which creates ongoing maintenance risk.
