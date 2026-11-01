import { Construction } from "lucide-react";
import { Card, PageHeader } from "./ui";

/** Honest placeholder for modules not built yet: says which stage delivers it and what it depends on. */
export function ComingSoon({ title, description, stage, items, blocker }: {
  title: string; description: string; stage: string; items: string[]; blocker?: string;
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <Card className="p-6 sm:p-8 max-w-3xl">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center size-10 rounded-md bg-accent-soft text-accent"><Construction className="size-5" aria-hidden /></span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-accent">{stage}</p>
            <p className="text-sm text-muted">Este módulo ainda não está disponível.</p>
          </div>
        </div>
        <h2 className="mt-6 text-sm font-semibold">O que vai entrar</h2>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2 text-sm text-muted">
          {items.map((i) => <li key={i} className="flex gap-2"><span className="mt-2 size-1 rounded-full bg-accent shrink-0" aria-hidden />{i}</li>)}
        </ul>
        {blocker && <p className="mt-6 rounded-md border border-warn/30 bg-warn/8 px-3 py-2.5 text-sm text-warn">{blocker}</p>}
      </Card>
    </>
  );
}
