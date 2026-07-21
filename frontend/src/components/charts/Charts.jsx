import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from "recharts";
import { inrShort, inr } from "@/lib/format";

const EMBER = "#ff682c";
const GRAPHITE = "#202020";
const BRASS = "#816729";
const ASH = "#c9c9c9";

const Tip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-graphite text-white text-xs px-3 py-2 rounded-md">
      <div className="font-display mb-1">{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color }}>{p.name}: {inr(p.value)}</div>
      ))}
    </div>
  );
};

export const RegimeCompareChart = ({ oldTax, newTax }) => {
  const data = [
    { name: "Old Regime", tax: oldTax, fill: GRAPHITE },
    { name: "New Regime", tax: newTax, fill: EMBER },
  ];
  return (
    <ResponsiveContainer width="100%" height={230}>
      <BarChart data={data} margin={{ top: 10, right: 8, left: 8, bottom: 0 }}>
        <XAxis dataKey="name" tick={{ fontSize: 13, fill: GRAPHITE }} axisLine={false} tickLine={false} />
        <YAxis tickFormatter={inrShort} tick={{ fontSize: 11, fill: "#828282" }} axisLine={false} tickLine={false} width={60} />
        <Tooltip content={<Tip />} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
        <Bar dataKey="tax" name="Tax liability" radius={[4, 4, 0, 0]} maxBarSize={90}>
          {data.map((d, i) => <Cell key={i} fill={d.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
};

export const SlabUtilChart = ({ slabs = [], color = EMBER }) => {
  const data = slabs.map((s) => ({ name: s.label, tax: s.tax, rate: s.rate }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, left: 4, bottom: 0 }}>
        <XAxis type="number" tickFormatter={inrShort} tick={{ fontSize: 10, fill: "#828282" }} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: GRAPHITE }} width={54} axisLine={false} tickLine={false} />
        <Tooltip content={<Tip />} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
        <Bar dataKey="tax" name="Tax in slab" radius={[0, 4, 4, 0]} fill={color} maxBarSize={22} />
      </BarChart>
    </ResponsiveContainer>
  );
};

export const DeductionDonut = ({ items = [] }) => {
  const COLORS = [GRAPHITE, EMBER, BRASS, "#a8a8a8", ASH];
  const data = items.filter((i) => i.value > 0);
  if (!data.length) return <div className="text-slate-ink text-sm py-16 text-center">No deductions captured yet.</div>;
  return (
    <ResponsiveContainer width="100%" height={230}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2} stroke="none">
          {data.map((d, i) => <Cell key={i} fill={d.color || COLORS[i % COLORS.length]} />)}
        </Pie>
        <Tooltip content={<Tip />} />
        <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
};
