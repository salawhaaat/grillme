import { useRef, useEffect, useState } from "react"
import { Sidebar } from "@/components/Sidebar"
import { cn } from "@/lib/utils"

type Tool = "pen" | "eraser" | "line" | "rect"
type Color = string

const COLORS: Color[] = [
  "#e2e8f0", // white-ish
  "#f87171", // red
  "#fb923c", // orange
  "#facc15", // yellow
  "#4ade80", // green
  "#60a5fa", // blue
  "#a78bfa", // purple
  "#f472b6", // pink
]

const SIZES = [2, 4, 8, 14]

interface Point { x: number; y: number }

export default function WhiteboardPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [tool, setTool] = useState<Tool>("pen")
  const [color, setColor] = useState<Color>("#e2e8f0")
  const [size, setSize] = useState(4)
  const drawing = useRef(false)
  const lastPoint = useRef<Point | null>(null)
  const snapshot = useRef<ImageData | null>(null)

  function getCtx() {
    return canvasRef.current?.getContext("2d") ?? null
  }

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const resize = () => {
      const { width, height } = canvas.parentElement!.getBoundingClientRect()
      const saved = getCtx()?.getImageData(0, 0, canvas.width, canvas.height)
      canvas.width = width
      canvas.height = height
      if (saved) getCtx()?.putImageData(saved, 0, 0)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas.parentElement!)
    return () => ro.disconnect()
  }, [])

  function point(e: React.MouseEvent): Point {
    const r = canvasRef.current!.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  function onMouseDown(e: React.MouseEvent) {
    drawing.current = true
    const p = point(e)
    lastPoint.current = p
    const ctx = getCtx()
    if (!ctx) return
    if (tool === "line" || tool === "rect") {
      snapshot.current = ctx.getImageData(0, 0, canvasRef.current!.width, canvasRef.current!.height)
    }
    if (tool === "pen" || tool === "eraser") {
      ctx.beginPath()
      ctx.moveTo(p.x, p.y)
    }
  }

  function onMouseMove(e: React.MouseEvent) {
    if (!drawing.current) return
    const ctx = getCtx()
    if (!ctx) return
    const p = point(e)

    ctx.lineWidth = size
    ctx.lineCap = "round"
    ctx.lineJoin = "round"

    if (tool === "pen") {
      ctx.globalCompositeOperation = "source-over"
      ctx.strokeStyle = color
      ctx.lineTo(p.x, p.y)
      ctx.stroke()
    } else if (tool === "eraser") {
      ctx.globalCompositeOperation = "destination-out"
      ctx.strokeStyle = "rgba(0,0,0,1)"
      ctx.lineTo(p.x, p.y)
      ctx.stroke()
    } else if (tool === "line" || tool === "rect") {
      ctx.globalCompositeOperation = "source-over"
      ctx.strokeStyle = color
      ctx.putImageData(snapshot.current!, 0, 0)
      ctx.beginPath()
      const start = lastPoint.current!
      if (tool === "line") {
        ctx.moveTo(start.x, start.y)
        ctx.lineTo(p.x, p.y)
        ctx.stroke()
      } else {
        ctx.strokeRect(start.x, start.y, p.x - start.x, p.y - start.y)
      }
    }
  }

  function onMouseUp() {
    drawing.current = false
    getCtx()?.beginPath()
  }

  function clearCanvas() {
    const canvas = canvasRef.current
    if (!canvas) return
    getCtx()?.clearRect(0, 0, canvas.width, canvas.height)
  }

  function downloadCanvas() {
    const canvas = canvasRef.current
    if (!canvas) return
    const a = document.createElement("a")
    a.href = canvas.toDataURL("image/png")
    a.download = "whiteboard.png"
    a.click()
  }

  const TOOLS: { id: Tool; icon: string; label: string }[] = [
    { id: "pen", icon: "edit", label: "Pen" },
    { id: "eraser", icon: "ink_eraser", label: "Eraser" },
    { id: "line", icon: "horizontal_rule", label: "Line" },
    { id: "rect", icon: "crop_square", label: "Rect" },
  ]

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-background">
      <header className="flex justify-between items-center w-full px-6 py-3 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-2">
          <img src="/logo.jpg" alt="grillme" className="h-9 w-9 rounded-full" />
          <span className="text-xl font-black tracking-tighter uppercase font-wordmark"><span className="text-on-surface">grill</span><span className="text-primary">me</span></span>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activePage="whiteboard" />

        {/* Toolbar */}
        <div className="w-16 flex flex-col items-center py-4 gap-4 border-r border-border bg-surface-container-low shrink-0">
          {/* Tools */}
          <div className="flex flex-col gap-1 w-full px-2">
            {TOOLS.map(({ id, icon, label }) => (
              <button
                key={id}
                title={label}
                onClick={() => setTool(id)}
                className={cn(
                  "flex flex-col items-center gap-0.5 py-2 rounded-xl w-full text-[9px] font-bold uppercase tracking-widest transition-colors",
                  tool === id
                    ? "bg-primary/15 text-primary"
                    : "text-outline hover:text-on-surface hover:bg-surface-container",
                )}
              >
                <span className="material-symbols-outlined text-lg">{icon}</span>
                {label}
              </button>
            ))}
          </div>

          <div className="w-8 h-px bg-outline-variant/30" />

          {/* Sizes */}
          <div className="flex flex-col items-center gap-2">
            {SIZES.map((s) => (
              <button
                key={s}
                onClick={() => setSize(s)}
                title={`${s}px`}
                className={cn(
                  "rounded-full bg-current transition-all",
                  size === s ? "text-primary" : "text-outline/40 hover:text-outline",
                )}
                style={{ width: Math.max(s, 4), height: Math.max(s, 4) }}
              />
            ))}
          </div>

          <div className="w-8 h-px bg-outline-variant/30" />

          {/* Colors */}
          <div className="flex flex-col items-center gap-1.5">
            {COLORS.map((c) => (
              <button
                key={c}
                onClick={() => setColor(c)}
                className={cn(
                  "w-5 h-5 rounded-full border-2 transition-all",
                  color === c ? "border-white scale-125" : "border-transparent hover:border-white/50",
                )}
                style={{ backgroundColor: c }}
              />
            ))}
          </div>

          <div className="mt-auto flex flex-col gap-2 px-2">
            <button
              title="Download"
              onClick={downloadCanvas}
              className="flex flex-col items-center gap-0.5 py-2 rounded-xl w-full text-[9px] font-bold uppercase tracking-widest text-outline hover:text-on-surface hover:bg-surface-container transition-colors"
            >
              <span className="material-symbols-outlined text-lg">download</span>
              Save
            </button>
            <button
              title="Clear"
              onClick={clearCanvas}
              className="flex flex-col items-center gap-0.5 py-2 rounded-xl w-full text-[9px] font-bold uppercase tracking-widest text-error hover:bg-error/10 transition-colors"
            >
              <span className="material-symbols-outlined text-lg">delete</span>
              Clear
            </button>
          </div>
        </div>

        {/* Canvas */}
        <div className="flex-1 overflow-hidden bg-surface-container-lowest relative">
          <div className="whiteboard-grid absolute inset-0 pointer-events-none opacity-40" />
          <canvas
            ref={canvasRef}
            className="absolute inset-0 cursor-crosshair"
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
          />
        </div>
      </div>
    </div>
  )
}
