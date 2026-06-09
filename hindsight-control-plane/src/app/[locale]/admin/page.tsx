"use client";

import { useTranslations } from "next-intl";
import { Settings } from "lucide-react";
import { AdminHeader } from "@/components/admin-header";
import { Sidebar } from "@/components/sidebar";
import { FeatureNotEnabled } from "@/components/feature-not-enabled";
import { AdminConfigView } from "@/components/admin-config-view";
import { useFeatures } from "@/lib/features-context";

export default function AdminPage() {
  const t = useTranslations("admin");
  const { features, loading } = useFeatures();

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <AdminHeader />

      <div className="flex flex-1 min-h-0">
        <Sidebar
          items={[
            { id: "configuration", label: t("configHeading"), icon: Settings, href: "/admin" },
          ]}
          currentTab="configuration"
        />

        <main className="flex-1 px-6 py-6 overflow-y-auto">
          <div className="max-w-5xl w-full mx-auto">
            {loading ? null : features?.admin_api ? (
              <AdminConfigView />
            ) : (
              <FeatureNotEnabled
                title={t("notEnabledTitle")}
                description={t.rich("notEnabledDescription", {
                  envVar: () => (
                    <code className="px-1 py-0.5 bg-muted rounded text-xs">
                      HINDSIGHT_API_ENABLE_ADMIN_API=true
                    </code>
                  ),
                })}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
