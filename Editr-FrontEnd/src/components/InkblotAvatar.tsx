import React, { useId, useMemo } from 'react';
import { motion } from 'motion/react';
import { MessageCircle } from 'lucide-react';
import type { InkblotVisualState } from '../lib/api';
import { cn } from '../lib/utils';

/** Safe fallback symmetric blob in viewBox 0 0 100 100 */
export const DEFAULT_INKBLOT_PATH_D =
  'M50 12 C68 18 88 38 82 58 C78 78 58 90 50 86 C42 90 22 78 18 58 C12 38 32 18 50 12 Z';

function isProbablyValidPathD(d: string): boolean {
  const t = d.trim();
  if (t.length < 8 || t.length > 8000) return false;
  if (/[<>]/.test(t)) return false;
  return /^[Mm]/.test(t);
}

export type InkblotAvatarStatus = 'idle' | 'thinking' | 'speaking';

interface InkblotAvatarProps {
  visual: InkblotVisualState | null;
  size?: number;
  status?: InkblotAvatarStatus;
  className?: string;
  /** When true and no valid visual, show lucide icon instead of default path */
  fallbackIcon?: boolean;
}

export function InkblotAvatar({
  visual,
  size = 44,
  status = 'idle',
  className,
  fallbackIcon = false,
}: InkblotAvatarProps) {
  const gradId = useId().replace(/:/g, '');
  const pathD = useMemo(() => {
    if (!visual || !isProbablyValidPathD(visual.svg_path_d)) {
      return null;
    }
    return visual.svg_path_d.trim();
  }, [visual]);

  const primary = visual?.primary_color ?? '#6B5B6B';
  const secondary = visual?.secondary_color ?? '#C4A8B8';
  const speed = visual?.animation_speed ?? 1;
  const baseDuration = 3 / Math.max(0.25, Math.min(3, speed));
  const thinkingScale = status === 'thinking' ? 1.08 : 1;
  const thinkingDuration = status === 'thinking' ? baseDuration * 0.45 : baseDuration;

  if (!pathD && fallbackIcon) {
    return (
      <MessageCircle
        size={Math.round(size * 0.55)}
        strokeWidth={2}
        className={cn('text-accent', className)}
        aria-hidden
      />
    );
  }

  const d = pathD ?? DEFAULT_INKBLOT_PATH_D;

  return (
    <motion.svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={cn('shrink-0 overflow-visible', className)}
      aria-hidden
      animate={
        status === 'thinking'
          ? { rotate: [0, 6, -6, 0] }
          : { rotate: 0 }
      }
      transition={
        status === 'thinking'
          ? { duration: 1.2, repeat: Infinity, ease: 'easeInOut' }
          : { duration: 0.2 }
      }
    >
      <defs>
        <linearGradient id={`inkblot-grad-${gradId}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={primary} />
          <stop offset="100%" stopColor={secondary} />
        </linearGradient>
      </defs>
      <motion.path
        d={d}
        fill={`url(#inkblot-grad-${gradId})`}
        stroke={secondary}
        strokeWidth={1.5}
        strokeOpacity={0.35}
        initial={false}
        animate={{
          scale: thinkingScale,
          scaleX: [1, 1.04, 0.98, 1],
          scaleY: [1, 0.98, 1.04, 1],
        }}
        transition={{
          duration: thinkingDuration,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
        style={{ transformOrigin: '50px 50px' }}
      />
    </motion.svg>
  );
}
