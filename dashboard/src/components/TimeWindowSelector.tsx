interface TimeWindowSelectorProps {
  value: number
  onChange: (seconds: number) => void
}

const OPTIONS = [5, 10, 30, 60]

export function TimeWindowSelector({ value, onChange }: TimeWindowSelectorProps) {
  return (
    <div className="flex gap-1">
      {OPTIONS.map((s) => {
        const isActive = value === s
        return (
          <button
            key={s}
            onClick={() => onChange(s)}
            className="px-4 py-1.5 text-[10px] tracking-widest uppercase border border-[#222] transition-colors duration-150 cursor-pointer"
            style={{
              color: isActive ? '#00fff5' : '#444',
              background: isActive ? 'rgba(0,255,245,0.05)' : 'transparent',
              borderColor: isActive ? 'rgba(0,255,245,0.2)' : '#222',
            }}
          >
            {s}s
          </button>
        )
      })}
    </div>
  )
}
