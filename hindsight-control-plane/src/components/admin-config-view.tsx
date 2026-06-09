"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Search } from "lucide-react";
import { client } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** Render a config value compactly: primitives inline, objects/arrays as JSON. */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value === "" ? '""' : value;
  if (typeof value === "boolean" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

/** Group key, derived from the first underscore-delimited token (e.g. "retain_chunk_size" -> "retain"). */
function groupOf(key: string): string {
  const head = key.split("_")[0];
  return head || "general";
}

export function AdminConfigView() {
  const t = useTranslations("admin");
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    client
      .getAdminConfig()
      .then((resp) => {
        if (!cancelled) {
          setConfig(resp.config);
          setError(false);
        }
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const groups = useMemo(() => {
    if (!config) return [];
    const needle = filter.trim().toLowerCase();
    const byGroup = new Map<string, [string, unknown][]>();
    for (const [key, value] of Object.entries(config).sort(([a], [b]) => a.localeCompare(b))) {
      if (
        needle &&
        !key.toLowerCase().includes(needle) &&
        !formatValue(value).toLowerCase().includes(needle)
      ) {
        continue;
      }
      const group = groupOf(key);
      const rows = byGroup.get(group) ?? [];
      rows.push([key, value]);
      byGroup.set(group, rows);
    }
    return [...byGroup.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [config, filter]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>{t("loading")}</span>
      </div>
    );
  }

  if (error) {
    return <p className="py-16 text-center text-sm text-destructive">{t("loadError")}</p>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">{t("configHeading")}</h2>
        <p className="text-sm text-muted-foreground">{t("configDescription")}</p>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t("searchPlaceholder")}
          className="pl-8"
        />
      </div>
      <p className="text-xs text-muted-foreground">{t("redactedHint")}</p>

      {groups.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">{t("empty")}</p>
      ) : (
        <div className="grid gap-4">
          {groups.map(([group, rows]) => (
            <Card key={group}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold capitalize text-foreground">
                  {group}
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <dl className="divide-y divide-border">
                  {rows.map(([key, value]) => (
                    <div key={key} className="grid grid-cols-1 gap-1 py-2 sm:grid-cols-3 sm:gap-4">
                      <dt className="font-mono text-xs text-muted-foreground break-all">{key}</dt>
                      <dd className="font-mono text-xs text-foreground break-all sm:col-span-2">
                        {formatValue(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
