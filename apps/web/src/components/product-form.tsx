"use client";

import type { Product, ProductStatus } from "@/lib/api";
import { centsToInput, parseMoney, STATUS_LABEL } from "@/lib/format";
import { Field, Input, Select, Textarea } from "./ui";

export interface ProductDraft {
  sku: string; name: string; brand: string; model: string; gtin: string; description: string;
  price: string; cost: string; stock: string; status: ProductStatus;
}

export function draftFrom(p?: Product): ProductDraft {
  return {
    sku: p?.sku ?? "", name: p?.name ?? "", brand: p?.brand ?? "", model: p?.model ?? "", gtin: p?.gtin ?? "",
    description: p?.description ?? "", price: centsToInput(p?.price_cents ?? null), cost: centsToInput(p?.cost_cents ?? null),
    stock: String(p?.stock ?? 0), status: p?.status ?? "draft",
  };
}

export type DraftErrors = Partial<Record<keyof ProductDraft, string>>;

/** Client-side checks for instant feedback only; the API validates everything again. */
export function toPayload(d: ProductDraft): { body?: Record<string, unknown>; errors: DraftErrors } {
  const errors: DraftErrors = {};
  if (!d.sku.trim()) errors.sku = "Informe o SKU.";
  else if (/\s/.test(d.sku.trim())) errors.sku = "O SKU não pode conter espaços.";
  if (!d.name.trim()) errors.name = "Informe o nome.";
  const price = parseMoney(d.price);
  const cost = parseMoney(d.cost);
  if (price === undefined) errors.price = "Valor inválido. Ex.: 129,90";
  if (cost === undefined) errors.cost = "Valor inválido. Ex.: 80,00";
  const stock = Number(d.stock || 0);
  if (!Number.isInteger(stock) || stock < 0) errors.stock = "Use um número inteiro maior ou igual a zero.";
  const gtin = d.gtin.replace(/\D/g, "");
  if (d.gtin.trim() && ![8, 12, 13, 14].includes(gtin.length)) errors.gtin = "GTIN/EAN tem 8, 12, 13 ou 14 dígitos.";
  if (Object.keys(errors).length) return { errors };
  return {
    errors,
    body: {
      sku: d.sku.trim(), name: d.name.trim(), brand: d.brand.trim(), model: d.model.trim(), gtin, description: d.description,
      price_cents: price, cost_cents: cost, stock, status: d.status,
    },
  };
}

export function ProductFields({ draft, onChange, errors, skuLocked, readOnly }: {
  draft: ProductDraft; onChange: (d: ProductDraft) => void; errors: DraftErrors; skuLocked?: boolean; readOnly?: boolean;
}) {
  const set = (k: keyof ProductDraft) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    onChange({ ...draft, [k]: e.target.value });
  const input = (k: keyof ProductDraft, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (id: string, d?: string) => (
    <Input id={id} aria-describedby={d} invalid={!!errors[k]} value={draft[k]} onChange={set(k)} readOnly={readOnly} {...props} />
  );
  return (
    <fieldset disabled={readOnly} className="grid gap-4 sm:grid-cols-2">
      <Field label="SKU" error={errors.sku} hint={skuLocked ? "O SKU identifica o produto e não muda aqui." : undefined}>
        {input("sku", { readOnly: skuLocked || readOnly, className: "font-mono", autoComplete: "off" })}
      </Field>
      <Field label="Status">{(id) => (
        <Select id={id} value={draft.status} onChange={set("status")}>
          {(["draft", "active", "archived"] as const).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </Select>
      )}</Field>
      <Field label="Nome" error={errors.name} className="sm:col-span-2">{input("name")}</Field>
      <Field label="Marca" error={errors.brand}>{input("brand")}</Field>
      <Field label="Modelo" error={errors.model}>{input("model")}</Field>
      <Field label="GTIN / EAN" error={errors.gtin} hint="Somente números.">{input("gtin", { inputMode: "numeric", className: "font-mono" })}</Field>
      <Field label="Estoque" error={errors.stock}>{input("stock", { inputMode: "numeric" })}</Field>
      <Field label="Preço de venda (R$)" error={errors.price}>{input("price", { inputMode: "decimal", placeholder: "0,00" })}</Field>
      <Field label="Preço de custo (R$)" error={errors.cost}>{input("cost", { inputMode: "decimal", placeholder: "0,00" })}</Field>
      <Field label="Descrição" className="sm:col-span-2">{(id) => <Textarea id={id} value={draft.description} onChange={set("description")} />}</Field>
    </fieldset>
  );
}
