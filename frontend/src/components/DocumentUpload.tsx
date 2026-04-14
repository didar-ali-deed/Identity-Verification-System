import { useCallback, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { Upload, X, FileImage, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface DocumentUploadProps {
  onFileSelected: (file: File) => void;
  isUploading: boolean;
  accept?: Record<string, string[]>;
  maxSize?: number;
  label?: string;
}

export default function DocumentUpload({
  onFileSelected,
  isUploading,
  accept = { "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"] },
  maxSize = 10 * 1024 * 1024,
  label = "Upload Document",
}: DocumentUploadProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: FileRejection[]) => {
      setError(null);
      if (rejectedFiles.length > 0) {
        setError(rejectedFiles[0].errors[0].message);
        return;
      }
      if (acceptedFiles.length > 0) {
        const file = acceptedFiles[0];
        setSelectedFile(file);
        const reader = new FileReader();
        reader.onload = () => setPreview(reader.result as string);
        reader.readAsDataURL(file);
      }
    },
    [],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    maxSize,
    multiple: false,
    disabled: isUploading,
  });

  const handleUpload = () => {
    if (selectedFile) onFileSelected(selectedFile);
  };

  const handleClear = () => {
    setPreview(null);
    setSelectedFile(null);
    setError(null);
  };

  return (
    <div className="space-y-3">
      <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-widest">
        {label}
      </label>

      {!preview ? (
        <div
          {...getRootProps()}
          className={cn(
            "border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all",
            isDragActive
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/40 hover:bg-primary/3",
            isUploading && "opacity-50 cursor-not-allowed",
          )}
        >
          <input {...getInputProps()} />
          <div
            className={cn(
              "w-12 h-12 rounded-xl border flex items-center justify-center mx-auto mb-3 transition-colors",
              isDragActive
                ? "bg-primary/10 border-primary/30"
                : "bg-muted border-border",
            )}
          >
            <Upload className={cn("h-5 w-5", isDragActive ? "text-primary" : "text-muted-foreground")} />
          </div>
          <p className="text-sm text-foreground font-medium">
            {isDragActive ? "Drop the file here" : "Drag & drop or click to browse"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            JPEG or PNG · max 10 MB
          </p>
        </div>
      ) : (
        <div className="border border-border rounded-xl overflow-hidden">
          <div className="relative">
            <img
              src={preview}
              alt="Document preview"
              className="w-full max-h-72 object-contain bg-[#020810]"
            />
            <button
              onClick={handleClear}
              disabled={isUploading}
              className="absolute top-2 right-2 p-1.5 bg-[#071428]/90 border border-border rounded-lg hover:bg-muted cursor-pointer border-solid disabled:opacity-50 transition-colors"
            >
              <X className="h-4 w-4 text-foreground" />
            </button>
          </div>
          <div className="px-4 py-3 bg-card border-t border-border flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <FileImage className="h-4 w-4 text-muted-foreground shrink-0" />
              <span className="text-sm text-foreground truncate">{selectedFile?.name}</span>
              <span className="text-xs text-muted-foreground shrink-0">
                ({((selectedFile?.size ?? 0) / 1024).toFixed(0)} KB)
              </span>
            </div>
            <button
              onClick={handleUpload}
              disabled={isUploading}
              className="px-4 py-1.5 bg-primary text-white rounded-lg text-sm font-semibold hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2 cursor-pointer border-none shrink-0 btn-glow transition-all"
            >
              {isUploading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Upload
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="text-xs text-red-400">{error}</p>
      )}
    </div>
  );
}
