import { Logo } from "@/components/shell";

const STEPS = ["Importar catálogo", "Organizar produtos", "Mapear template oficial", "Validar e corrigir", "Gerar planilha"];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh grid lg:grid-cols-[1fr_minmax(440px,560px)]">
      <section className="hidden lg:flex flex-col justify-between border-r border-line bg-bg-2 p-12 relative overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute -right-40 -top-40 size-[520px] rounded-full bg-accent/[0.07] blur-3xl" />
        <Logo />
        <div className="relative max-w-lg">
          <p className="text-sm font-semibold uppercase tracking-[0.12em] text-accent">Marketplace Listing Automation</p>
          <h1 className="mt-4 max-w-md text-balance text-[42px] leading-[1.08] font-extrabold tracking-tight">
            Do catálogo à planilha oficial, sem retrabalho.
          </h1>
          <p className="mt-5 text-muted leading-relaxed">
            Centralize milhares de produtos, encontre inconsistências antes do envio e prepare anúncios em massa
            com rastreabilidade de cada lote.
          </p>
          <ol className="mt-10 flex flex-col gap-3">
            {STEPS.map((s, i) => (
              <li key={s} className="flex items-center gap-3 text-sm">
                <span className="grid place-items-center size-7 rounded-md border border-line bg-card font-mono text-xs text-accent-2">{i + 1}</span>
                <span className="text-muted">{s}</span>
              </li>
            ))}
          </ol>
        </div>
        <p className="relative text-xs text-faint">Exportar uma planilha não publica anúncios. O envio ao marketplace sempre passa por você.</p>
      </section>
      <section className="flex flex-col justify-center px-4 sm:px-10 py-12">
        <div className="lg:hidden mb-10"><Logo /></div>
        <div className="w-full max-w-sm mx-auto">{children}</div>
      </section>
    </div>
  );
}
