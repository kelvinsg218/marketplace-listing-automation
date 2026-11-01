"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type Me } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Alert, Button, Field, Input } from "@/components/ui";

export default function RegisterPage() {
  const { setMe } = useSession();
  const router = useRouter();
  const [form, setForm] = useState({ name: "", email: "", password: "", organization_name: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const shortPassword = form.password.length > 0 && form.password.length < 10;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setMe(await api<Me>("/auth/register", { method: "POST", body: form }));
      router.replace("/painel/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao criar a conta.");
      setBusy(false);
    }
  }

  return (
    <>
      <h2 className="text-2xl font-bold tracking-tight">Criar conta</h2>
      <p className="mt-1 mb-8 text-sm text-muted">Você será o proprietário da organização e poderá convidar a equipe depois.</p>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {error && <Alert>{error}</Alert>}
        <Field label="Seu nome">{(id) => <Input id={id} autoComplete="name" required value={form.name} onChange={set("name")} />}</Field>
        <Field label="Empresa">{(id) => <Input id={id} autoComplete="organization" required value={form.organization_name} onChange={set("organization_name")} />}</Field>
        <Field label="E-mail">{(id) => <Input id={id} type="email" autoComplete="email" required value={form.email} onChange={set("email")} />}</Field>
        <Field label="Senha" hint="Pelo menos 10 caracteres." error={shortPassword ? "Pelo menos 10 caracteres." : undefined}>
          {(id, d) => <Input id={id} type="password" autoComplete="new-password" required aria-describedby={d} invalid={shortPassword} value={form.password} onChange={set("password")} />}
        </Field>
        <Button type="submit" variant="primary" busy={busy} className="w-full mt-2">Criar conta</Button>
      </form>
      <p className="mt-8 text-sm text-muted text-center">
        Já tem conta? <Link href="/entrar/" className="text-accent hover:text-accent-2 font-medium">Entrar</Link>
      </p>
    </>
  );
}
