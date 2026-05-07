import { create } from "zustand";

interface EditModeState {
  editing: boolean;
  toggle: () => void;
  setEditing: (v: boolean) => void;
}

/**
 * Zustand store for toggling inline edit mode.
 * Used on the quotas page to enable/disable inline cell editing.
 */
export const useEditMode = create<EditModeState>((set) => ({
  editing: false,
  toggle: () => set((state) => ({ editing: !state.editing })),
  setEditing: (v: boolean) => set({ editing: v }),
}));
