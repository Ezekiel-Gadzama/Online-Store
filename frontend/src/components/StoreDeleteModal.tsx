import { useState } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle } from 'lucide-react'
import { storesApi } from '../api/stores'
import { formatApiError } from '../utils/apiError'

export default function StoreDeleteModal({
  storeName,
  storeId,
  open,
  onClose,
  onDeleted,
}: {
  storeName: string
  storeId: number
  open: boolean
  onClose: () => void
  onDeleted: () => void
}) {
  const [step, setStep] = useState<'confirm' | 'otp'>('confirm')
  const [otp, setOtp] = useState('')
  const [info, setInfo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!open) return null

  const requestOtp = async () => {
    setError(null)
    setBusy(true)
    try {
      const res = await storesApi.requestDeleteOtp(storeId)
      setInfo(res.message)
      setStep('otp')
    } catch (e: unknown) {
      setError(formatApiError(e, 'Could not send verification code'))
    } finally {
      setBusy(false)
    }
  }

  const submitDelete = async () => {
    setError(null)
    if (otp.trim().length !== 6) {
      setError('Enter the 6-digit code from your business email.')
      return
    }
    setBusy(true)
    try {
      await storesApi.deleteStore(storeId, otp.trim())
      onDeleted()
      onClose()
      setStep('confirm')
      setOtp('')
      setInfo(null)
    } catch (e: unknown) {
      setError(formatApiError(e, 'Could not delete store'))
    } finally {
      setBusy(false)
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md border-2 border-red-300 overflow-hidden">
        <div className="bg-red-50 border-b border-red-200 px-6 py-4">
          <h2 className="flex items-center gap-2 text-lg font-bold text-red-800">
            <AlertTriangle className="h-6 w-6 shrink-0 text-red-600" aria-hidden />
            Delete Store {storeName}
          </h2>
        </div>
        <div className="p-6">
        <p className="text-sm text-red-900/90 mb-4">
          This permanently removes <strong className="text-red-800">{storeName}</strong> — settings, products,
          orders, templates, and API connections. A verification code will be sent to the business admin email.
        </p>
        {step === 'confirm' ? (
          <div className="flex justify-end gap-2">
            <button type="button" className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              disabled={busy}
              className="px-4 py-2 text-sm font-semibold bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 shadow-sm"
              onClick={requestOtp}
            >
              {busy ? 'Sending…' : 'Send verification code'}
            </button>
          </div>
        ) : (
          <>
            {info && <p className="text-sm text-green-700 mb-3">{info}</p>}
            <label className="block text-sm font-medium text-gray-700 mb-1">Verification code</label>
            <input
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm mb-3 tracking-widest"
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000"
              inputMode="numeric"
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button type="button" className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md" onClick={onClose}>
                Cancel
              </button>
              <button
                type="button"
                disabled={busy}
                className="px-4 py-2 text-sm font-semibold bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 shadow-sm"
                onClick={submitDelete}
              >
                {busy ? 'Deleting…' : `Delete Store ${storeName}`}
              </button>
            </div>
          </>
        )}
        {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
        </div>
      </div>
    </div>,
    document.body,
  )
}