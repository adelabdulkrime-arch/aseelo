"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { Alert, ErrorState, Field, LoadingState, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Brand, BrandUpdate } from "@/lib/types";

const COLOR_FIELDS = [
  { key: "primary_color", labelKey: "primaryColor" },
  { key: "secondary_color", labelKey: "secondaryColor" },
  { key: "accent_color", labelKey: "accentColor" },
] as const;

export default function BrandPage() {
  const { t } = useI18n();

  const [brand, setBrand] = useState<Brand | null>(null);
  const [form, setForm] = useState<BrandUpdate>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  /** Mirror the server's stored brand into the form. */
  function syncForm(result: Brand) {
    setBrand(result);
    setForm({
      brand_name: result.brand_name,
      primary_color: result.primary_color,
      secondary_color: result.secondary_color,
      accent_color: result.accent_color,
      phone: result.phone ?? "",
      whatsapp: result.whatsapp ?? "",
      website: result.website ?? "",
      address: result.address ?? "",
      tagline: result.tagline ?? "",
    });
  }

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      syncForm(await api.getBrand());
    } catch (cause) {
      setLoadError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  function update<K extends keyof BrandUpdate>(key: K, value: BrandUpdate[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      // Empty strings mean "clear this field"; the API accepts null for that.
      const payload = Object.fromEntries(
        Object.entries(form).map(([key, value]) =>
          typeof value === "string" && value.trim() === "" ? [key, null] : [key, value],
        ),
      ) as BrandUpdate;
      // Re-sync: the API normalises values (bare domains gain https://, colours
      // are upper-cased), and the user should see what was actually stored.
      syncForm(await api.updateBrand(payload));
      setSaved(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
    } finally {
      setSaving(false);
    }
  }

  async function handleLogo(file: File) {
    setError(null);
    setUploading(true);
    try {
      setBrand(await api.uploadLogo(file));
      setSaved(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("somethingWrong"));
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  if (loadError) return <ErrorState message={loadError} onRetry={load} />;
  if (!brand) return <LoadingState />;

  return (
    <div className="animate-fade-in space-y-5">
      <header>
        <h1 className="text-2xl font-bold">{t("brand")}</h1>
        <p className="mt-1 text-sm text-ink-muted">{t("brandSubtitle")}</p>
      </header>

      {error && <Alert kind="error">{error}</Alert>}
      {saved && !error && <Alert kind="success">{t("saved")}</Alert>}

      <section className="card p-5">
        <h2 className="mb-3 font-bold">{t("logo")}</h2>
        <div className="flex items-center gap-4">
          <div className="grid h-20 w-20 shrink-0 place-items-center overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
            {brand.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- media comes from the API/S3 host
              <img src={brand.logo_url} alt={brand.brand_name} className="h-full w-full object-contain" />
            ) : (
              <span className="text-2xl text-slate-400" aria-hidden="true">
                ◈
              </span>
            )}
          </div>
          <div>
            <input
              ref={fileInput}
              id="logo"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleLogo(file);
              }}
            />
            <label htmlFor="logo" className="btn-secondary cursor-pointer">
              {uploading && <Spinner className="h-4 w-4" />}
              {brand.logo_url ? t("changeLogo") : t("uploadLogo")}
            </label>
            <p className="mt-1.5 text-xs text-ink-muted">{t("logoHint")}</p>
          </div>
        </div>
      </section>

      <form onSubmit={handleSubmit} className="space-y-5">
        <section className="card space-y-4 p-5">
          <Field label={t("brandName")} htmlFor="brand_name">
            <input
              id="brand_name"
              className="input"
              value={form.brand_name ?? ""}
              onChange={(e) => update("brand_name", e.target.value)}
              maxLength={120}
              required
            />
          </Field>

          <Field label={t("tagline")} htmlFor="tagline">
            <input
              id="tagline"
              className="input"
              value={form.tagline ?? ""}
              onChange={(e) => update("tagline", e.target.value)}
              maxLength={160}
            />
          </Field>
        </section>

        <section className="card p-5">
          <h2 className="mb-3 font-bold">{t("colors")}</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {COLOR_FIELDS.map(({ key, labelKey }) => (
              <Field key={key} label={t(labelKey)} htmlFor={key}>
                <div className="flex items-center gap-2">
                  <input
                    id={key}
                    type="color"
                    className="h-10 w-12 shrink-0 cursor-pointer rounded-lg border border-slate-300 bg-white p-1"
                    value={form[key] ?? "#000000"}
                    onChange={(e) => update(key, e.target.value.toUpperCase())}
                    aria-label={t(labelKey)}
                  />
                  <input
                    className="input font-mono text-sm uppercase"
                    value={form[key] ?? ""}
                    onChange={(e) => update(key, e.target.value.toUpperCase())}
                    dir="ltr"
                    pattern="#[0-9A-Fa-f]{6}"
                    maxLength={7}
                  />
                </div>
              </Field>
            ))}
          </div>
        </section>

        <section className="card p-5">
          <h2 className="mb-3 font-bold">{t("contactInfo")}</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("phone")} htmlFor="phone">
              <input
                id="phone"
                className="input"
                value={form.phone ?? ""}
                onChange={(e) => update("phone", e.target.value)}
                dir="ltr"
                maxLength={40}
              />
            </Field>
            <Field label={t("whatsapp")} htmlFor="whatsapp">
              <input
                id="whatsapp"
                className="input"
                value={form.whatsapp ?? ""}
                onChange={(e) => update("whatsapp", e.target.value)}
                dir="ltr"
                maxLength={40}
              />
            </Field>
            <Field label={t("website")} htmlFor="website">
              <input
                id="website"
                className="input"
                value={form.website ?? ""}
                onChange={(e) => update("website", e.target.value)}
                dir="ltr"
                maxLength={255}
              />
            </Field>
            <Field label={t("address")} htmlFor="address">
              <input
                id="address"
                className="input"
                value={form.address ?? ""}
                onChange={(e) => update("address", e.target.value)}
                maxLength={255}
              />
            </Field>
          </div>
        </section>

        <div className="flex justify-end">
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving && <Spinner className="h-4 w-4" />}
            {saving ? t("saving") : t("save")}
          </button>
        </div>
      </form>
    </div>
  );
}
