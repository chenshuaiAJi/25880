export function formatMoney(value: string | null): string {
  if (value === null || value === "") {
    return ""
  }
  const negative = value.startsWith("-")
  const [intPart, fraction = "00"] = value.replace("-", "").split(".")
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",")
  return `${negative ? "-" : ""}${grouped}.${fraction.padEnd(2, "0").slice(0, 2)}`
}

export function batchLabel(batchNo: number, label = ""): string {
  if (label !== "") {
    return label
  }
  return batchNo === 0 ? "无括号" : `(${batchNo})`
}

export function sourceLabel(source: string): string {
  if (source === "shipment") {
    return "发货单"
  }
  if (source === "remittance") {
    return "汇款表"
  }
  return source
}

export function monthLabel(year: number, month: number): string {
  return `${year}年${month}月`
}
