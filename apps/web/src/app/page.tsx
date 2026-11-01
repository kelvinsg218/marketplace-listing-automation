"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";
import { Skeleton } from "@/components/ui";

export default function Home() {
  const { me, loading } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (!loading) router.replace(me ? "/painel/" : "/entrar/");
  }, [loading, me, router]);
  return <div className="min-h-dvh grid place-items-center"><Skeleton className="h-8 w-40" /></div>;
}
