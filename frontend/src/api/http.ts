export class ApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "ApiError"
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

export function readString(record: Record<string, unknown>, key: string): string {
  const value = record[key]
  if (typeof value !== "string") {
    throw new ApiError(`字段 ${key} 格式不正确`)
  }
  return value
}

export function readNullableString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key]
  if (value === null) {
    return null
  }
  if (typeof value !== "string") {
    throw new ApiError(`字段 ${key} 格式不正确`)
  }
  return value
}

export function readNumber(record: Record<string, unknown>, key: string): number {
  const value = record[key]
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ApiError(`字段 ${key} 格式不正确`)
  }
  return value
}

export function readStringArray(record: Record<string, unknown>, key: string): string[] {
  const value = record[key]
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new ApiError(`字段 ${key} 格式不正确`)
  }
  return value
}

export async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response
  const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body === undefined || isFormData ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError("无法连接对账服务，请确认 http://127.0.0.1:8787 已启动")
  }
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ApiError("服务返回的不是 JSON")
  }
  if (!response.ok) {
    throw new ApiError(readErrorMessage(body))
  }
  return body
}

function readErrorMessage(body: unknown): string {
  if (!isRecord(body)) {
    return "请求失败"
  }
  const error = body.error
  if (isRecord(error) && typeof error.message === "string" && error.message.trim() !== "") {
    return error.message
  }
  return "请求失败"
}
