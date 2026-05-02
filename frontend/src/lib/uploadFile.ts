/**
 * 파일 업로드 헬퍼.
 * spec: POST /api/rooms/{roomId}/files (multipart/form-data, field name: "file")
 *
 * 클라이언트 측 사전 검증 — 잘못된 확장자/큰 파일은 즉시 reject (UX).
 * 단, 서버 검증이 단일 진실 — 결과 코드(INVALID_TYPE/TOO_LARGE/INVALID_ROOM)는 그대로 surface.
 */

import type { FileAttachment } from "@/types"

export const ALLOWED_EXTENSIONS = [".pdf", ".txt", ".md", ".csv"] as const
export const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB

export type UploadErrorCode = "INVALID_TYPE" | "TOO_LARGE" | "INVALID_ROOM" | "NETWORK" | "WRITE_FAILED" | "UNKNOWN"

export class UploadError extends Error {
  code: UploadErrorCode
  constructor(code: UploadErrorCode, message: string) {
    super(message)
    this.code = code
  }
}

export function getFileExt(filename: string): string {
  const dot = filename.lastIndexOf(".")
  return dot < 0 ? "" : filename.slice(dot).toLowerCase()
}

export function isAllowedExtension(filename: string): boolean {
  return (ALLOWED_EXTENSIONS as readonly string[]).includes(getFileExt(filename))
}

export function preflightCheck(file: File): UploadError | null {
  if (!isAllowedExtension(file.name)) {
    return new UploadError(
      "INVALID_TYPE",
      `허용되지 않은 확장자입니다 (${ALLOWED_EXTENSIONS.join(", ")} 만 가능)`,
    )
  }
  if (file.size > MAX_FILE_SIZE) {
    return new UploadError("TOO_LARGE", "파일 크기가 10MB를 초과합니다")
  }
  return null
}

export type UploadResponse = FileAttachment

/**
 * 단일 파일 업로드. 진행률 콜백 지원 — XMLHttpRequest 사용.
 */
export function uploadFile(
  roomId: string,
  file: File,
  onProgress?: (loaded: number, total: number) => void,
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const pre = preflightCheck(file)
    if (pre) {
      reject(pre)
      return
    }

    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append("file", file)

    xhr.open("POST", `/api/rooms/${encodeURIComponent(roomId)}/files`)

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded, e.total)
    }

    xhr.onerror = () => {
      reject(new UploadError("NETWORK", "네트워크 오류가 발생했습니다"))
    }

    xhr.onload = () => {
      let body: unknown = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        // ignore
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        const r = body as Partial<UploadResponse> & {
          filename?: string
          extraction?: "ready" | "summarizing" | "error"
          extraction_mode?: "raw" | "summary" | "truncated" | "error"
          degraded?: boolean
          extraction_error?: string | null
        }
        if (!r || typeof r.path !== "string") {
          reject(new UploadError("UNKNOWN", "잘못된 서버 응답"))
          return
        }
        // server returns { path, size, mime, filename, extraction, extraction_mode, degraded, extraction_error }
        const filename =
          r.filename ?? r.path.split("/").pop() ?? file.name
        resolve({
          path: r.path,
          filename,
          size: r.size ?? file.size,
          mime: r.mime ?? file.type,
          extraction: r.extraction,
          extraction_mode: r.extraction_mode,
          degraded: r.degraded,
          extraction_error: r.extraction_error,
        })
      } else {
        const r = body as { code?: UploadErrorCode; error?: string } | null
        const code = r?.code ?? "UNKNOWN"
        const msg = r?.error ?? `업로드 실패 (HTTP ${xhr.status})`
        reject(new UploadError(code as UploadErrorCode, msg))
      }
    }

    xhr.send(form)
  })
}
