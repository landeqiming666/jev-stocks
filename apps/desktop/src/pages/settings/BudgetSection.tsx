import { useState } from "react";
import { Button, Field, Input } from "../../components/ui";
import { settings as text } from "../../i18n/zh-CN/settings";
import { BUDGET_MAX, BUDGET_MIN, validateBudget, validateLookback } from "./validation";
import type { SettingsController } from "./useSettings";
import { useDraft } from "./useDraft";
import { Section } from "./Section";

export function BudgetSection({ state }: { state: SettingsController }) {
  const budget = useDraft(String(state.settings!.dailyTokenBudget)), lookback = useDraft(String(state.settings!.firstScanLookbackDays));
  const [budgetError, setBudgetError] = useState<string>(), [lookbackError, setLookbackError] = useState<string>();
  const valid = validateBudget(budget.value);
  async function save() {
    const submitted = budget.value, days = lookback.value;
    const tokenResult = validateBudget(submitted), dayResult = validateLookback(days);
    setBudgetError(tokenResult.error); setLookbackError(dayResult.error);
    if (!tokenResult.ok || !dayResult.ok) return;
    if (await state.update({ dailyTokenBudget: tokenResult.value, firstScanLookbackDays: dayResult.value }, text.budgetSaved)) {
      budget.accept(submitted); lookback.accept(days);
    }
  }
  return <Section title={text.sections[2]}><form noValidate onSubmit={event => { event.preventDefault(); void save(); }}>
    <div className="p-settings__budget">
      <Field id="daily-budget" label={text.budget} help={`${BUDGET_MIN}–${BUDGET_MAX}`} error={budgetError}>
        <Input numeric inputMode="numeric" value={budget.value} onChange={event => { budget.edit(event.target.value); setBudgetError(undefined); }}
          onBlur={() => setBudgetError(validateBudget(budget.value).error)} />
      </Field>
      <div className="p-settings__estimate"><span className="p-settings__help">{text.estimate}</span>
        <strong className="u-mono">{valid.ok ? `≈ $${(Math.round(valid.value / 2000000 * 0.084 * 100) / 100).toFixed(2)}` : "—"}</strong>
        <span className="p-settings__help">{text.estimateHelp}</span></div>
      <Field id="lookback" label={text.lookback} help={text.lookbackHelp} error={lookbackError}>
        <Input numeric inputMode="numeric" value={lookback.value} onChange={event => { lookback.edit(event.target.value); setLookbackError(undefined); }}
          onBlur={() => setLookbackError(validateLookback(lookback.value).error)} />
      </Field>
    </div><Button type="submit" disabled={!!state.busy}>{text.saveBudget}</Button>
  </form></Section>;
}
