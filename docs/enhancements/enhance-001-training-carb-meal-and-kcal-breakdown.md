# Enhancement Brief: enhance-001 Training Carb Meal and Kcal Breakdown

## Problem statement
The current meal plan output does not model training carbs as a dedicated meal and does not show calories per meal. This makes training-day plans harder to follow and prevents users from validating per-meal energy distribution against the day total.

## Goals
- Insert a dedicated `training` meal when training carbs are prescribed (`training carbs > 0g`).
- Allow placing the `training` meal before any meal using existing `--training-before` sequencing behavior.
- Show calories (`kcal`) per meal in addition to macros.
- Ensure meal-level kcal totals reconcile to total day energy (`TDEE + training calorie demand`), while non-training meals target `TDEE + demand - supply`.

## In scope
- Add conditional creation of a `training` meal in meal-plan generation when proposed training carbs are greater than `0g`.
- Reuse `--training-before` insertion logic to determine where `training` appears in the meal sequence (one `training` meal maximum per day).
- Allow syntactic parsing of `--training-before=training`, but reject it with a deterministic semantic runtime error.
- Define `training` meal macro composition as carbs-only (`carbs_g=training_carbs_g`, `protein_g=0`, `fat_g=0`).
- Differentiate:
  - training calorie demand (from total zone minutes, including zone 1),
  - training fueling (all Z1 => 0g, else 60g carbs/hour),
  - training calorie supply (`training_carbs_g * 4`).
- Add per-meal kcal output for all meals in the meal plan.
- Add a reconciliation step that adjusts evening snack displayed kcal so summed meal kcal equals total day kcal (`TDEE + training calorie demand`) with small rounding corrections.
- Update tests for training meal insertion and kcal display/reconciliation behavior.
- Update canonical core docs because this enhancement changes output contracts/behavior.

## Out of scope
- Allowing training after evening snack.
- Introducing a new CLI option for training insertion behavior.
- Changing daily macro targets or optimization strategy beyond the specified meal insertion and kcal reconciliation.

## Constraints and assumptions
- `--training-before` can reference insertion before any meal, but `training` as target must fail semantic validation at runtime.
- If training carbs are `0g`, no `training` meal is added.
- `training` meal uses carbs only; protein and fat remain `0`.
- Kcal per meal is derived from meal macros using existing macro-to-kcal conventions, except final evening-snack display-only kcal correction for reconciliation.
- Small rounding differences are expected and should be corrected only via evening snack displayed-kcal adjustment so final summed meal kcal matches `(TDEE + training calorie demand)`.
- This enhancement intentionally accepts that training cannot be scheduled after evening snack.

## Definition of done
- For plans with training carbs `> 0g`, output includes a `training` meal at the position implied by `--training-before`.
- For plans with training carbs `= 0g`, no `training` meal is present.
- Passing `training` to `--training-before` is accepted syntactically but rejected with a deterministic semantic runtime error.
- `training` meal macros are `carbs_g=training_carbs_g`, `protein_g=0`, `fat_g=0`.
- Meal plan output includes `kcal` per meal alongside macros.
- Sum of displayed meal kcal equals `(TDEE + training calorie demand)`, with minor rounding delta absorbed by evening snack displayed kcal only.
- Automated tests cover:
  - Training meal insertion and ordering behavior.
  - No-training-meal case when training carbs are zero.
  - Semantic rejection behavior for `--training-before=training`.
  - Training meal carbs-only macro composition.
  - Per-meal kcal calculation/display.
  - Kcal reconciliation to exact `(TDEE + training calorie demand)`.
  - Macro grams unchanged by display-only kcal reconciliation.

## Open questions (optional)
- None for this enhancement scope after clarifications.
