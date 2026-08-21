import { useEffect, useState, type FormEvent } from "react";

import type {
  AgentTransport,
  ProviderProfile,
  ProviderStatus,
  ProviderTestResult,
} from "../contracts/agent-transport.ts";
import { useI18n } from "../i18n/I18nProvider.tsx";

export function ProviderSettingsPanel({ transport }: { transport: AgentTransport }) {
  const { t } = useI18n();
  const [profiles, setProfiles] = useState<ProviderProfile[]>([]);
  const [providerId, setProviderId] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [modelId, setModelId] = useState("");
  const [key, setKey] = useState("");
  const [status, setStatus] = useState<ProviderStatus | null>(null);
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void transport.providers.list().then((nextProfiles) => {
      if (!active) return;
      setProfiles(nextProfiles);
      const selected = nextProfiles[0];
      if (selected) {
        setProviderId(selected.id);
        setEndpoint(selected.endpoint);
        setModelId(selected.modelId);
        setStatus({
          id: selected.id,
          configured: selected.configured,
          fingerprint: selected.fingerprint,
        });
      }
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => { active = false; };
  }, [transport]);

  const chooseProfile = (id: string) => {
    setProviderId(id);
    const profile = profiles.find((candidate) => candidate.id === id);
    if (!profile) return;
    setEndpoint(profile.endpoint);
    setModelId(profile.modelId);
    setStatus({ id, configured: profile.configured, fingerprint: profile.fingerprint });
    setKey("");
    setTestResult(null);
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!providerId.trim() || !endpoint.trim() || !modelId.trim() || !key) return;
    setBusy(true);
    setError(null);
    try {
      const next = await transport.providers.saveKey({
        id: providerId.trim(),
        endpoint: endpoint.trim(),
        modelId: modelId.trim(),
        key,
      });
      setStatus(next);
      setKey("");
      setProfiles(await transport.providers.list());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!providerId) return;
    setBusy(true);
    try {
      setStatus(await transport.providers.removeKey(providerId));
      setKey("");
      setTestResult(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const testProvider = async () => {
    if (!providerId) return;
    setBusy(true);
    try {
      setTestResult(await transport.providers.test(providerId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="nta-provider-settings" onSubmit={save} autoComplete="off">
      <h2>{t("providerSettings")}</h2>
      {profiles.length > 0 && (
        <label>
          {t("providerId")}
          <select value={providerId} onChange={(event) => chooseProfile(event.target.value)}>
            {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.label}</option>)}
          </select>
        </label>
      )}
      {profiles.length === 0 && (
        <label>{t("providerId")}<input value={providerId} onChange={(event) => setProviderId(event.target.value)} /></label>
      )}
      <label>{t("endpoint")}<input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} /></label>
      <label>{t("modelId")}<input value={modelId} onChange={(event) => setModelId(event.target.value)} /></label>
      <label>{t("apiKey")}<input type="password" value={key} onChange={(event) => setKey(event.target.value)} /></label>
      <p className="nta-provider-status">
        {status?.configured ? t("configured") : t("notConfigured")}
        {status?.fingerprint ? ` · ${status.fingerprint}` : ""}
      </p>
      {testResult && <p className={testResult.ok ? "" : "nta-error"}>{testResult.ok ? "OK" : testResult.error}</p>}
      {error && <p className="nta-error" role="alert">{error}</p>}
      <div className="nta-provider-actions">
        <button type="submit" disabled={busy || !key}>{t("save")}</button>
        <button type="button" disabled={busy || !status?.configured} onClick={() => void testProvider()}>{t("test")}</button>
        <button type="button" disabled={busy || !status?.configured} onClick={() => void remove()}>{t("remove")}</button>
      </div>
    </form>
  );
}
