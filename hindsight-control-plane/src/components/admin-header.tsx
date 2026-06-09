"use client";

import { useTranslations } from "next-intl";
import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, Moon, ShieldCheck, Sun, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "@/components/language-switcher";
import { useTheme } from "@/lib/theme-context";
import { useFeatures } from "@/lib/features-context";
import { withBasePath } from "@/lib/base-path";

/**
 * Header for the global admin surface.
 *
 * Deliberately NOT the bank-scoped BankSelector: the admin area is not tied to a
 * memory bank, so it shows a back-to-app link, the admin title, and global controls
 * (theme, language, logout) instead of the bank dropdown / add-document actions.
 */
export function AdminHeader() {
  const tNav = useTranslations("nav");
  const t = useTranslations("admin");
  const { theme, toggleTheme } = useTheme();
  const { features } = useFeatures();

  return (
    <header className="bg-card text-card-foreground px-5 py-3 border-b-4 border-primary-gradient">
      <div className="flex items-center gap-4 text-sm">
        {/* Logo → back to app */}
        <Link href="/dashboard" title={tNav("home")}>
          <Image
            src={withBasePath("/logo.png")}
            alt="Hindsight"
            width={40}
            height={40}
            className="h-10 w-auto"
            unoptimized
          />
        </Link>

        <div className="h-8 w-px bg-border" />

        {/* Admin title */}
        <div className="flex items-center gap-2 font-bold">
          <ShieldCheck className="h-5 w-5 text-primary" />
          <span>{t("title")}</span>
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Back to app */}
        <Link
          href="/dashboard"
          className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          <span className="text-sm font-medium">{t("backToApp")}</span>
        </Link>

        <div className="h-8 w-px bg-border" />

        {/* Dark Mode Toggle */}
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          className="h-9 w-9"
          title={theme === "light" ? tNav("darkMode") : tNav("lightMode")}
        >
          {theme === "light" ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
        </Button>

        <LanguageSwitcher />

        {features?.access_key_auth && (
          <>
            <div className="h-8 w-px bg-border" />
            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9"
              title="Logout"
              onClick={async () => {
                try {
                  await fetch(withBasePath("/api/auth/logout"), { method: "POST" });
                } finally {
                  window.location.href = withBasePath("/login");
                }
              }}
            >
              <LogOut className="h-5 w-5" />
            </Button>
          </>
        )}
      </div>
    </header>
  );
}
