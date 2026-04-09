"use client";
import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchSumTransactions } from "./api";
import type { Transaction, Totals, SortState } from "./types";
import { calcTotals, sortData, buildMarkets } from "./helpers";

export default function PageSumTransactions() {
  const [data, setData] = useState<Transaction[]>([]);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [sort, setSort] = useState<SortState>({ col: "pair", dir: "asc" });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTransactions().then(res => {
      setData(res); setTotals(calcTotals(res)); setLoading(false);
    });
  }, []);

  const sorted = sortData(data, sort);
  return (
    <Card>
      <CardContent>
        {loading ? <Skeleton /> : <DataTable rows={sorted} totals={totals} />}
      </CardContent>
    </Card>
  );
}
