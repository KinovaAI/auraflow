"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, Loader2, X, Check } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { videoApi, type VideoCategory } from "@/lib/video-api";

export function CategoryManager() {
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");

  const { data: categories, isLoading } = useQuery({
    queryKey: ["video-categories"],
    queryFn: () => videoApi.listCategories().then((r) => r.data.data),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      videoApi.createCategory({
        name: formName.trim(),
        description: formDescription.trim() || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-categories"] });
      toast.success("Category created");
      resetForm();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to create category");
    },
  });

  const updateMutation = useMutation({
    mutationFn: (categoryId: string) =>
      videoApi.updateCategory(categoryId, {
        name: formName.trim(),
        description: formDescription.trim() || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-categories"] });
      toast.success("Category updated");
      resetForm();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to update category");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (categoryId: string) => videoApi.deleteCategory(categoryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-categories"] });
      toast.success("Category deleted");
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to delete category");
    },
  });

  function resetForm() {
    setShowAddForm(false);
    setEditingId(null);
    setFormName("");
    setFormDescription("");
  }

  function startEdit(cat: VideoCategory) {
    setEditingId(cat.id);
    setFormName(cat.name);
    setFormDescription(cat.description || "");
    setShowAddForm(false);
  }

  function handleDelete(cat: VideoCategory) {
    if (
      cat.video_count > 0 &&
      !window.confirm(
        `"${cat.name}" has ${cat.video_count} video(s). Videos will be uncategorized. Delete anyway?`
      )
    ) {
      return;
    }
    deleteMutation.mutate(cat.id);
  }

  const isPending =
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-700">Video Categories</h3>
        {!showAddForm && !editingId && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              resetForm();
              setShowAddForm(true);
            }}
          >
            <Plus className="mr-1 h-4 w-4" />
            Add Category
          </Button>
        )}
      </div>

      {/* Add form */}
      {showAddForm && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-4">
          <div className="space-y-3">
            <div>
              <Label htmlFor="cat-name">Name</Label>
              <Input
                id="cat-name"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g., Yoga Flows"
              />
            </div>
            <div>
              <Label htmlFor="cat-desc">Description (optional)</Label>
              <Input
                id="cat-desc"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder="Short description..."
              />
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={() => createMutation.mutate()}
                disabled={!formName.trim() || isPending}
              >
                {createMutation.isPending && (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                )}
                Create
              </Button>
              <Button size="sm" variant="ghost" onClick={resetForm}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Category list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
        </div>
      ) : !categories?.length && !showAddForm ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-8 text-center">
          <p className="text-sm text-gray-500">No categories yet</p>
          <p className="mt-1 text-xs text-gray-400">
            Create categories to organize your video library.
          </p>
        </div>
      ) : (
        <div className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {categories?.map((cat) => (
            <div key={cat.id} className="px-4 py-3">
              {editingId === cat.id ? (
                /* Inline edit form */
                <div className="space-y-3">
                  <div>
                    <Label htmlFor={`edit-name-${cat.id}`}>Name</Label>
                    <Input
                      id={`edit-name-${cat.id}`}
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor={`edit-desc-${cat.id}`}>Description</Label>
                    <Input
                      id={`edit-desc-${cat.id}`}
                      value={formDescription}
                      onChange={(e) => setFormDescription(e.target.value)}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => updateMutation.mutate(cat.id)}
                      disabled={!formName.trim() || isPending}
                      className="rounded-md p-1.5 text-green-600 hover:bg-green-50 disabled:opacity-50"
                    >
                      {updateMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Check className="h-4 w-4" />
                      )}
                    </button>
                    <button
                      onClick={resetForm}
                      className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ) : (
                /* Display row */
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-gray-900">
                        {cat.name}
                      </p>
                      {!cat.is_active && (
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                          Inactive
                        </span>
                      )}
                    </div>
                    {cat.description && (
                      <p className="mt-0.5 text-xs text-gray-500">
                        {cat.description}
                      </p>
                    )}
                    <p className="mt-0.5 text-xs text-gray-400">
                      {cat.video_count} video{cat.video_count !== 1 ? "s" : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => startEdit(cat)}
                      className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(cat)}
                      disabled={isPending}
                      className="rounded-md p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
