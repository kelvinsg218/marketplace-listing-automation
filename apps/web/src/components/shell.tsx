"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Boxes, ChevronsUpDown, FileSpreadsheet, FolderTree, History, Images, LayoutDashboard, LifeBuoy, Workflow, Layers, LogOut, Menu, Network, PackageOpen,
  Settings, Store, Upload, Users, Wrench, X,
} from "lucide-react";
import { useRequireSession, useSession } from "@/lib/session";
import { ROLE_LABEL } from "@/lib/format";
import { cx, Skeleton } from "./ui";

interface NavItem { href: string; label: string; icon: React.ElementType; soon?: boolean }
const NAV: { section: string; items: NavItem[] }[] = [
  { section: "", items: [{ href: "/painel/", label: "Painel", icon: LayoutDashboard }] },
  {
    section: "Catálogo", items: [
      { href: "/catalogo/", label: "Produtos", icon: Boxes },
      { href: "/categorias/", label: "Categorias", icon: FolderTree },
      { href: "/fotos/", label: "Central de Fotos", icon: Images },
      { href: "/importacoes/", label: "Importações", icon: Upload },
      { href: "/compatibilidades/", label: "Compatibilidades", icon: Wrench, soon: true },
    ],
  },
  {
    section: "Anúncios", items: [
      { href: "/anuncios-em-massa/", label: "Anúncios em massa", icon: Layers },
      { href: "/templates/", label: "Templates", icon: FileSpreadsheet },
      { href: "/lotes/", label: "Lotes e exportações", icon: PackageOpen },
      { href: "/assistente/", label: "Assistente de Correção", icon: LifeBuoy },
      { href: "/regras/", label: "Regras adaptativas", icon: Workflow },
      { href: "/marketplaces/", label: "Marketplaces", icon: Store },
    ],
  },
  {
    section: "Gestão", items: [
      { href: "/historico/", label: "Histórico", icon: History },
      { href: "/organizacao/", label: "Organização", icon: Users },
      { href: "/configuracoes/", label: "Configurações", icon: Settings, soon: true },
    ],
  },
];

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2.5", className)}>
      <span className="grid place-items-center size-8 rounded-md bg-accent text-on-accent">
        <Network className="size-[18px]" strokeWidth={2.4} aria-hidden />
      </span>
      <span className="text-[17px] font-extrabold tracking-tight">MLA<span className="text-accent">.</span></span>
    </span>
  );
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <nav aria-label="Principal" className="flex flex-col gap-4 [@media(max-height:820px)]:gap-3">
      {NAV.map((group) => (
        <div key={group.section}>
          {group.section && <p className="px-3 mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-faint">{group.section}</p>}
          <ul className="flex flex-col gap-0.5">
            {group.items.map(({ href, label, icon: Icon, soon }) => {
              const active = path.startsWith(href);
              return (
                <li key={href}>
                  <Link href={href} onClick={onNavigate} aria-current={active ? "page" : undefined}
                    className={cx("group relative flex items-center gap-3 rounded-md px-3 h-8 [@media(max-height:820px)]:h-7 text-sm transition-colors",
                      active ? "bg-card text-fg" : "text-muted hover:text-fg hover:bg-card/60")}>
                    {active && <span className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full bg-accent" aria-hidden />}
                    <Icon className={cx("size-[18px] shrink-0", active ? "text-accent" : "text-faint group-hover:text-muted")} aria-hidden />
                    <span className="min-w-0 truncate">{label}</span>
                    {soon && <span className="ml-auto shrink-0 whitespace-nowrap text-[10px] font-medium text-faint border border-line rounded px-1.5 py-px">em breve</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function OrgSwitcher() {
  const { me, org, role, switchOrg } = useSession();
  if (!me || !org) return null;
  return (
    <label className="relative flex items-center gap-3 rounded-md border border-line bg-bg-2 px-3 py-2 hover:border-line-strong">
      <span className="grid place-items-center size-8 shrink-0 rounded-md bg-card text-sm font-bold text-accent-2">
        {org.name.slice(0, 1).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold">{org.name}</span>
        <span className="block text-xs text-faint">{ROLE_LABEL[role ?? ""]}</span>
      </span>
      {me.memberships.length > 1 && <ChevronsUpDown className="size-4 text-faint" aria-hidden />}
      {me.memberships.length > 1 && (
        <select aria-label="Trocar de organização" value={org.id} onChange={(e) => switchOrg(e.target.value)}
          className="absolute inset-0 opacity-0 cursor-pointer">
          {me.memberships.map((m) => <option key={m.organization.id} value={m.organization.id}>{m.organization.name}</option>)}
        </select>
      )}
    </label>
  );
}

function UserFooter() {
  const { me, logout } = useSession();
  const router = useRouter();
  if (!me) return null;
  return (
    <div className="flex items-center gap-3 border-t border-line pt-4">
      <span className="grid place-items-center size-8 rounded-full bg-card text-xs font-semibold text-muted">
        {me.user.name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{me.user.name}</span>
        <span className="block truncate text-xs text-faint">{me.user.email}</span>
      </span>
      <button aria-label="Sair" title="Sair" onClick={async () => { await logout(); router.replace("/entrar/"); }}
        className="rounded-md p-2 text-faint hover:text-fg hover:bg-card">
        <LogOut className="size-4" />
      </button>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { me, org, loading } = useRequireSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const path = usePathname();
  useEffect(() => setMenuOpen(false), [path]);

  if (loading || !me) {
    return (
      <div className="min-h-dvh grid place-items-center" aria-busy>
        <Skeleton className="h-8 w-40" />
      </div>
    );
  }

  const sidebar = (
    <div className="flex h-full flex-col gap-4 px-3 py-4">
      <div className="px-2"><Logo /></div>
      <OrgSwitcher />
      <div className="flex-1 overflow-y-auto -mx-1 px-1"><Nav onNavigate={() => setMenuOpen(false)} /></div>
      <UserFooter />
    </div>
  );

  return (
    <div className="min-h-dvh lg:pl-[272px]">
      <aside className="hidden lg:block fixed inset-y-0 left-0 w-[272px] border-r border-line bg-bg-2">{sidebar}</aside>

      <header className="lg:hidden sticky top-0 z-40 flex h-14 items-center justify-between border-b border-line bg-bg/90 backdrop-blur px-4">
        <Logo />
        <button onClick={() => setMenuOpen(true)} aria-label="Abrir menu" className="rounded-md p-2 text-muted hover:text-fg">
          <Menu className="size-5" />
        </button>
      </header>
      {menuOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMenuOpen(false)} aria-hidden />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-bg-2 border-r border-line">
            <button onClick={() => setMenuOpen(false)} aria-label="Fechar menu" className="absolute right-3 top-4 rounded-md p-1.5 text-muted hover:text-fg">
              <X className="size-5" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <main className="mx-auto w-full max-w-[1400px] px-4 sm:px-6 lg:px-10 py-6 lg:py-9">
        {org ? children : <p className="text-muted">Sua conta não participa de nenhuma organização.</p>}
      </main>
    </div>
  );
}
