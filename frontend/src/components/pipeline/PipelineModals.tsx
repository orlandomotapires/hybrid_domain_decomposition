import React from 'react';
import { AlertTriangle, FileCode } from 'lucide-react';
import { Demonstrator, SimulationConfig, SimulationParameters } from '../../types/pipeline';

/* Save Preset Modal */
interface SavePresetModalProps {
  demonstrator: Demonstrator;
  newPresetName: string;
  setNewPresetName: (value: string) => void;
  onSavePreset: (filename: string) => Promise<void>;
  onClose: () => void;
}

export const SavePresetModal: React.FC<SavePresetModalProps> = ({
  demonstrator,
  newPresetName,
  setNewPresetName,
  onSavePreset,
  onClose,
}) => (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4">
        <h3 className="text-base font-bold text-white">Save Parameters as New Preset</h3>
        <p className="text-xs text-slate-400">
          Creates a new JSON preset inside <code>simulations/{demonstrator.id}/data/</code> and sets it active.
        </p>
        <input
          type="text"
          value={newPresetName}
          onChange={(e) => setNewPresetName(e.target.value)}
          placeholder="e.g. qa_medium_preset.json"
          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
        />
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={() => onClose()}
            className="px-4 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={async () => {
              if (!newPresetName.trim()) return;
              await onSavePreset(newPresetName.trim());
              setNewPresetName('');
              onClose();
            }}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500"
          >
            Save & Activate
          </button>
        </div>
      </div>
    </div>
);

/* Raw JSON Modal */
interface RawJsonModalProps {
  config: SimulationConfig;
  parameters: SimulationParameters;
  onClose: () => void;
}

export const RawJsonModal: React.FC<RawJsonModalProps> = ({ config, parameters, onClose }) => (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-4xl w-full max-h-[85vh] flex flex-col overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileCode className="w-4 h-4 text-indigo-400" />
            <span className="font-bold text-sm text-white">
              Live Configuration & Parameters JSON Preview
            </span>
          </div>
          <button
            type="button"
            onClick={() => onClose()}
            className="px-3 py-1 rounded-lg text-xs bg-slate-800 text-slate-300 hover:bg-slate-700"
          >
            Close
          </button>
        </div>
        <div className="p-5 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="min-w-0">
            <div className="text-xs font-mono text-indigo-300 mb-2">
              data/simulation_config.json
            </div>
            <pre className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto">
              {JSON.stringify(config, null, 2)}
            </pre>
          </div>
          <div className="min-w-0">
            <div className="text-xs font-mono text-indigo-300 mb-2">
              data/{config.parameters_file_path}
            </div>
            <pre className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto">
              {JSON.stringify(parameters, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
);

/* Rename Matrix Modal */
interface RenameMatrixModalProps {
  demonstrator: Demonstrator;
  renameValue: string;
  setRenameValue: (value: string) => void;
  onRenameDemonstrator: (demId: string, newName: string) => Promise<void>;
  onClose: () => void;
}

export const RenameMatrixModal: React.FC<RenameMatrixModalProps> = ({
  demonstrator,
  renameValue,
  setRenameValue,
  onRenameDemonstrator,
  onClose,
}) => (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4">
        <h3 className="text-base font-bold text-white">
          Rename simulation ({demonstrator.id})
        </h3>
        <p className="text-xs text-slate-400">
          Renames the folder inside <code>simulations/</code> while preserving all
          its parameter presets and run history.
        </p>
        <input
          type="text"
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          placeholder="e.g. simulation_01_blade_qa"
          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-white"
        />
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={() => onClose()}
            className="px-4 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={async () => {
              const trimmed = renameValue.trim();
              if (!trimmed || trimmed === demonstrator.id) {
                onClose();
                return;
              }
              await onRenameDemonstrator(demonstrator.id, trimmed);
              onClose();
            }}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500"
          >
            Rename Folder
          </button>
        </div>
      </div>
    </div>
);

/* Delete Matrix Confirmation Modal */
interface DeleteMatrixModalProps {
  demonstrator: Demonstrator;
  onDeleteDemonstrator: (demId: string) => Promise<void>;
  onClose: () => void;
}

export const DeleteMatrixModal: React.FC<DeleteMatrixModalProps> = ({
  demonstrator,
  onDeleteDemonstrator,
  onClose,
}) => (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-rose-500/40 rounded-2xl max-w-md w-full p-6 space-y-4">
        <div className="flex items-center gap-2.5 text-rose-400">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <h3 className="text-base font-bold text-white">
            Delete simulation &quot;{demonstrator.id}&quot;?
          </h3>
        </div>
        <p className="text-xs text-slate-300 leading-relaxed">
          This will permanently remove <code>simulations/{demonstrator.id}/</code> along with
          its parameter presets and saved run folders. Its matrix stays in the library.
        </p>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={() => onClose()}
            className="px-4 py-2 rounded-lg text-xs text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={async () => {
              await onDeleteDemonstrator(demonstrator.id);
              onClose();
            }}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-rose-600 text-white hover:bg-rose-500"
          >
            Delete Permanently
          </button>
        </div>
      </div>
    </div>
);

/* Generate Synthetic Mesh Confirmation Modal */
