import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { useApp } from "../App.jsx";
import { Empty, Field, Section, useAsync } from "../components/ui.jsx";

export default function Settings() {
  const { t, notify, health } = useApp();
  const data = useAsync(() => api.settings(), []);
  const [model, setModel] = useState("");
  const [language, setLanguage] = useState("es");
  const [busy, setBusy] = useState(false);
  const s = data.data;
  useEffect(() => {
    if (s) { setModel(s.model || ""); setLanguage(s.default_language || "es"); }
  }, [s]);

  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      await api.settingsUpdate({ model: model.trim(), default_language: language });
      notify(t("saved"));
      data.reload();
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  };
  if (data.error) return <Empty>{data.error.code === "network" ? t("network_error") : data.error.message}</Empty>;
  if (!s) return <div className="help" role="status">{t("loading")}</div>;
  const models = Array.isArray(s.models) ? s.models : [];

  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-[22px] font-semibold">{t("nav_settings")}</h1>
      <form onSubmit={save} className="space-y-4">
        <Section title={t("settings_model")}>
          <p className="help mb-2">{t("settings_model_help")}</p>
          <Field label={t("settings_model_name")}>
            <input className="field mono" list="model-options" value={model} onChange={(e) => setModel(e.target.value)} placeholder={t("settings_model_auto")} />
          </Field>
          <datalist id="model-options">{models.map((m) => <option key={m} value={m} />)}</datalist>
        </Section>
        <Section title={t("settings_language")}>
          <Field label={t("settings_language_label")} help={t("settings_language_help")}>
            <select className="field" style={{ maxWidth: 240 }} value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="es">{t("lang_es")}</option>
              <option value="en">{t("lang_en")}</option>
            </select>
          </Field>
        </Section>
        <button type="submit" className="btn btn-primary" disabled={busy}>{t("save")}</button>
      </form>
      <Section title={t("about")}>
        <div className="help">Cicero's Hoard {health?.version || ""}</div>
        <div className="help">{t("credits")}</div>
      </Section>
    </div>
  );
}
