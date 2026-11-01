const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const int = new Intl.NumberFormat("pt-BR");
const dateTime = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

export const money = (cents: number | null | undefined) => (cents == null ? "—" : brl.format(cents / 100));
export const count = (n: number | null | undefined) => (n == null ? "—" : int.format(n));
export const when = (iso: string) => dateTime.format(new Date(iso));

/** "R$ 1.234,56" / "1234.56" / "25" -> cents; empty -> null; garbage -> undefined. */
export function parseMoney(text: string): number | null | undefined {
  const t = text.replace(/R\$|\s/g, "");
  if (!t) return null;
  const normalized = t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t;
  if (!/^\d+(\.\d{0,2})?$/.test(normalized)) return undefined;
  return Math.round(parseFloat(normalized) * 100);
}

export const centsToInput = (cents: number | null) => (cents == null ? "" : (cents / 100).toFixed(2).replace(".", ","));

export const ROLE_LABEL: Record<string, string> = {
  owner: "Proprietário", admin: "Administrador", editor: "Editor", viewer: "Leitor",
};

export const STATUS_LABEL: Record<string, string> = { draft: "Rascunho", active: "Ativo", archived: "Arquivado" };

const ACTIONS: Record<string, string> = {
  "org.created": "criou a organização",
  "product.created": "cadastrou o produto",
  "product.updated": "editou o produto",
  "product.deleted": "excluiu o produto",
  "member.added": "adicionou um membro",
  "member.removed": "removeu um membro",
  "member.role_changed": "alterou o papel de um membro",
  "variant.created": "criou a variação",
  "variant.updated": "editou a variação",
  "variant.deleted": "excluiu a variação",
  "image.uploaded": "enviou uma foto do produto",
  "image.urls_added": "registrou URLs de fotos do produto",
  "image.deleted": "excluiu uma foto do produto",
  "seller_account.created": "cadastrou uma conta de vendedor",
  "seller_account.deleted": "removeu uma conta de vendedor",
  "template.uploaded": "registrou um template oficial",
  "template.updated": "atualizou um template",
  "template.mapping_saved": "salvou um mapeamento",
  "batch.created": "criou um lote",
  "batch.exported": "gerou a planilha de um lote",
  "rule.created": "criou uma regra",
  "rule.updated": "alterou uma regra",
  "rule.reverted": "reverteu uma regra",
};

export function describeEvent(action: string, details: Record<string, unknown>): string {
  const base = ACTIONS[action] ?? action;
  const sku = typeof details.sku === "string" ? ` ${details.sku}` : "";
  return base + sku;
}
