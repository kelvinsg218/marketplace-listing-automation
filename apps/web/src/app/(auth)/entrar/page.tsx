"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError, type Me } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Alert, Button, Field, Input } from "@/components/ui";

function safeReturn(path: string | null) {
  // Only same-site relative paths: never an open redirect.
  return path && path.startsWith("/") && !path.startsWith("//") ? path : "/painel/";
}

function LoginForm() {
  const { setMe } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setMe(await api<Me>("/auth/login", { method: "POST", body: { email, password } }));
      router.replace(safeReturn(params.get("voltar")));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao entrar.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      {error && <Alert>{error}</Alert>}
      <Field label="E-mail">{(id) => (
        <Input id={id} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      )}</Field>
      <Field label="Senha">{(id) => (
        <Input id={id} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      )}</Field>
      <div className="flex justify-end -mt-1">
        <Link href="/recuperar-senha/" className="text-[13px] text-muted hover:text-accent">Esqueci minha senha</Link>
      </div>
      <Button type="submit" variant="primary" busy={busy} className="w-full">Entrar</Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <>
      <h2 className="text-2xl font-bold tracking-tight">Entrar</h2>
      <p className="mt-1 mb-8 text-sm text-muted">Acesse o painel da sua empresa.</p>
      <Suspense><LoginForm /></Suspense>
      <p className="mt-8 text-sm text-muted text-center">
        Ainda não tem conta? <Link href="/cadastro/" className="text-accent hover:text-accent-2 font-medium">Criar conta</Link>
      </p>
    </>
  );
}
