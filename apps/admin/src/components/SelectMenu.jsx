import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';

/**
 * A styled replacement for <select>.
 *
 * The native popup is drawn by the OS: it cannot be themed, it ignores the
 * page's dark mode, and at ~25 templates it renders as a tall system list that
 * escapes the panel. This draws the list in the document instead, so it matches
 * the surrounding cards and can show a disabled option's reason.
 *
 * Keyboard behaviour follows the native control: Up/Down move through the
 * options and skip disabled ones, Enter or Space commits, Escape closes without
 * changing anything, Home/End jump to the ends.
 *
 * options: [{ value, label, disabled?, title?, suffix? }]
 */
export default function SelectMenu({
    value,
    onChange,
    options,
    placeholder = 'Select...',
    leftIcon = null,
    className = '',
    buttonClassName = '',
    disabled = false,
    ariaLabel,
}) {
    const [open, setOpen] = useState(false);
    const [activeIndex, setActiveIndex] = useState(-1);
    const rootRef = useRef(null);
    const listRef = useRef(null);

    const selected = useMemo(
        () => options.find(o => o.value === value) || null,
        [options, value],
    );

    const firstEnabled = useCallback(
        (from, step) => {
            for (let i = from; i >= 0 && i < options.length; i += step) {
                if (!options[i].disabled) return i;
            }
            return -1;
        },
        [options],
    );

    // Opening seeds the highlight from the current selection, so arrow keys
    // continue from where the user is. Done in the handler rather than an
    // effect: deriving it on open is the event, not a synchronisation.
    const openMenu = useCallback(() => {
        const idx = options.findIndex(o => o.value === value);
        setActiveIndex(idx >= 0 && !options[idx].disabled ? idx : firstEnabled(0, 1));
        setOpen(true);
    }, [options, value, firstEnabled]);

    // Close on an outside click or a scroll of an ancestor, matching what a
    // native popup does rather than leaving the list floating over the page.
    useEffect(() => {
        if (!open) return undefined;
        const onDown = (e) => {
            if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener('mousedown', onDown);
        return () => document.removeEventListener('mousedown', onDown);
    }, [open]);

    // Keep the highlighted row in view when moving by keyboard.
    useEffect(() => {
        if (!open || activeIndex < 0 || !listRef.current) return;
        const el = listRef.current.children[activeIndex];
        if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
    }, [open, activeIndex]);

    const commit = (opt) => {
        if (!opt || opt.disabled) return;
        onChange(opt.value);
        setOpen(false);
    };

    const onKeyDown = (e) => {
        if (disabled) return;
        if (!open) {
            if (['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(e.key)) {
                e.preventDefault();
                openMenu();
            }
            return;
        }
        switch (e.key) {
            case 'Escape':
                e.preventDefault();
                setOpen(false);
                break;
            case 'ArrowDown':
                e.preventDefault();
                setActiveIndex(i => { const n = firstEnabled(i + 1, 1); return n === -1 ? i : n; });
                break;
            case 'ArrowUp':
                e.preventDefault();
                setActiveIndex(i => { const n = firstEnabled(i - 1, -1); return n === -1 ? i : n; });
                break;
            case 'Home':
                e.preventDefault();
                setActiveIndex(firstEnabled(0, 1));
                break;
            case 'End':
                e.preventDefault();
                setActiveIndex(firstEnabled(options.length - 1, -1));
                break;
            case 'Enter':
            case ' ':
                e.preventDefault();
                commit(options[activeIndex]);
                break;
            default:
                break;
        }
    };

    return (
        <div ref={rootRef} className={`relative ${className}`}>
            <button
                type="button"
                disabled={disabled}
                onClick={() => (open ? setOpen(false) : openMenu())}
                onKeyDown={onKeyDown}
                aria-haspopup="listbox"
                aria-expanded={open}
                aria-label={ariaLabel}
                className={`w-full flex items-center ${leftIcon ? 'pl-12' : 'pl-5'} pr-10 py-3.5 bg-slate-50 dark:bg-slate-900 border rounded-2xl text-sm font-bold text-left dark:text-white outline-none shadow-inner transition-shadow hover:shadow-md focus:ring-2 focus:ring-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed ${
                    open ? 'border-indigo-400 dark:border-indigo-500' : 'border-slate-200 dark:border-slate-700'
                } ${disabled ? '' : 'cursor-pointer'} ${buttonClassName}`}
            >
                {leftIcon && (
                    <span className={`absolute left-4 top-1/2 -translate-y-1/2 transition-colors ${open ? 'text-indigo-500' : 'text-slate-400'}`}>
                        {leftIcon}
                    </span>
                )}
                <span className={`truncate ${selected ? '' : 'text-slate-400 dark:text-slate-500'}`}>
                    {selected ? selected.label : placeholder}
                </span>
                <span className="absolute inset-y-0 right-0 flex items-center px-4 pointer-events-none text-slate-400">
                    <ChevronDown className={`w-5 h-5 transition-transform ${open ? 'rotate-180' : ''}`} />
                </span>
            </button>

            {open && (
                <ul
                    ref={listRef}
                    role="listbox"
                    tabIndex={-1}
                    onKeyDown={onKeyDown}
                    className="absolute z-50 mt-2 w-full max-h-72 overflow-y-auto custom-scrollbar rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-2xl py-1.5"
                >
                    {options.map((opt, i) => {
                        const isSelected = opt.value === value;
                        const isActive = i === activeIndex;
                        return (
                            <li
                                key={opt.value}
                                role="option"
                                aria-selected={isSelected}
                                aria-disabled={opt.disabled || undefined}
                                title={opt.title}
                                onMouseEnter={() => !opt.disabled && setActiveIndex(i)}
                                onClick={() => commit(opt)}
                                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-bold transition-colors ${
                                    opt.disabled
                                        ? 'text-slate-300 dark:text-slate-600 cursor-not-allowed'
                                        : `cursor-pointer ${isActive ? 'bg-indigo-50 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300' : 'text-slate-700 dark:text-slate-200'}`
                                }`}
                            >
                                <span className="w-4 shrink-0">
                                    {isSelected && !opt.disabled && <Check className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />}
                                </span>
                                <span className="truncate">{opt.label}</span>
                                {opt.suffix && (
                                    <span className="ml-auto shrink-0 text-[10px] font-black uppercase tracking-widest text-slate-400">
                                        {opt.suffix}
                                    </span>
                                )}
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}
