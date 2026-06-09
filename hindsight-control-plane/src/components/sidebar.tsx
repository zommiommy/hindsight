"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import Link from "next/link";

export interface SidebarItem {
  /** Stable id compared against `currentTab` to mark the active entry. */
  id: string;
  label: string;
  icon: LucideIcon;
  /** Destination href (Next.js applies basePath automatically). */
  href: string;
}

interface SidebarProps {
  /** Navigation entries to render, top to bottom. */
  items: SidebarItem[];
  /** Id of the active entry. */
  currentTab: string;
  /**
   * Optional in-app navigation handler. When provided, a plain left-click is
   * intercepted and routed via the callback (middle-click / Cmd+click still open
   * the href in a new tab). When omitted, the entry behaves as a normal link.
   */
  onTabChange?: (id: string) => void;
}

/**
 * Collapsible left navigation, shared across the app (bank workspace, admin, …).
 * It is purely presentational: callers provide the items, the active id, and an
 * optional click handler.
 */
export function Sidebar({ items, currentTab, onTabChange }: SidebarProps) {
  const t = useTranslations("bank.sidebar");
  const [isCollapsed, setIsCollapsed] = useState(true);

  return (
    <aside
      className={cn(
        "bg-card border-r border-border flex flex-col transition-all duration-300",
        isCollapsed ? "w-16" : "w-64"
      )}
    >
      <nav className="flex-1 p-3 pt-4">
        <ul className="space-y-1">
          {items.map((item) => {
            const Icon = item.icon;
            const isActive = currentTab === item.id;

            return (
              <li key={item.id}>
                <Link
                  href={item.href}
                  onClick={(e) => {
                    // For left-click, prevent default and use the callback so the
                    // parent can navigate without a full page reload. Middle-click
                    // or Ctrl/Cmd+click open in a new tab naturally.
                    if (onTabChange && e.button === 0 && !e.ctrlKey && !e.metaKey) {
                      e.preventDefault();
                      onTabChange(item.id);
                    }
                  }}
                  className={cn(
                    "w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all",
                    isActive
                      ? "bg-primary-gradient text-white shadow-sm"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    isCollapsed && "justify-center px-0"
                  )}
                  title={isCollapsed ? item.label : undefined}
                >
                  <Icon className="w-5 h-5 flex-shrink-0" />
                  {!isCollapsed && <span>{item.label}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Collapse/Expand button at bottom */}
      <div className="p-3 border-t border-border">
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className={cn(
            "w-full flex items-center gap-3 px-4 py-2 rounded-lg text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors",
            isCollapsed && "justify-center px-0"
          )}
          title={isCollapsed ? t("expandSidebar") : t("collapseSidebar")}
        >
          {isCollapsed ? (
            <ChevronRight className="w-5 h-5" />
          ) : (
            <>
              <ChevronLeft className="w-5 h-5" />
              <span>{t("collapse")}</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
