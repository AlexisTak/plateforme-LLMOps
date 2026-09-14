export type SimulatorInput = {
  setupPrice: number;
  monthlyPrice: number;
  clients: number;
  humanCost: number;
  infraCost: number;
  llmCost: number;
  cac: number;
  churnPct: number;
  salesCost: number;
};

export type SimulatorResult = {
  monthlyRevenue: number;
  annualRevenue: number;
  mrr: number;
  arr: number;
  grossMargin: number;
  netMarginEstimate: number;
  breakEvenMonths: number | null;
  roi: number | null;
  clientsFor100k: number;
  clientsFor500k: number;
  clientsFor1M: number;
};

export function simulate(input: SimulatorInput): SimulatorResult {
  const { setupPrice, monthlyPrice, clients, humanCost, infraCost, llmCost, cac, salesCost } = input;

  const setupRevenue = setupPrice * clients;
  const mrr = monthlyPrice * clients;
  const arr = mrr * 12;
  const monthlyRevenue = mrr;
  const annualRevenue = setupRevenue + arr;

  const variableCostPerClient = infraCost + llmCost;
  const grossMargin = mrr - variableCostPerClient * clients;
  const fixedMonthlyCost = humanCost + salesCost;
  const acquisitionCost = cac * clients;
  const netMarginEstimate = grossMargin - fixedMonthlyCost;

  const upfront = setupRevenue - acquisitionCost;
  const monthlyNet = grossMargin - fixedMonthlyCost;
  const breakEvenMonths = upfront >= 0 ? 0 : monthlyNet > 0 ? Math.ceil(-upfront / monthlyNet) : null;

  const revenuePerClient = setupPrice + monthlyPrice * 12;
  const clientsFor100k = revenuePerClient > 0 ? Math.ceil(100000 / revenuePerClient) : Infinity;
  const clientsFor500k = revenuePerClient > 0 ? Math.ceil(500000 / revenuePerClient) : Infinity;
  const clientsFor1M = revenuePerClient > 0 ? Math.ceil(1000000 / revenuePerClient) : Infinity;

  const roi = acquisitionCost > 0 ? ((annualRevenue - acquisitionCost) / acquisitionCost) * 100 : null;

  return {
    monthlyRevenue,
    annualRevenue,
    mrr,
    arr,
    grossMargin,
    netMarginEstimate,
    breakEvenMonths,
    roi,
    clientsFor100k,
    clientsFor500k,
    clientsFor1M,
  };
}

if (process.env.NODE_ENV !== "production") {
  const example = simulate({
    setupPrice: 15000,
    monthlyPrice: 2500,
    clients: 20,
    humanCost: 0,
    infraCost: 0,
    llmCost: 0,
    cac: 0,
    churnPct: 0,
    salesCost: 0,
  });
  console.assert(example.mrr === 50000, "simulate(): MRR attendu 50000", example.mrr);
  console.assert(example.arr === 600000, "simulate(): ARR attendu 600000", example.arr);
  console.assert(example.annualRevenue === 900000, "simulate(): CA an1 attendu 900000", example.annualRevenue);
}
