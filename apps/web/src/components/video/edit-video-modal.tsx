"use client";

import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { videoApi, type Video } from "@/lib/video-api";

interface EditVideoModalProps {
  video: Video;
  onClose: () => void;
  onSaved: () => void;
}

export function EditVideoModal({
  video,
  onClose,
  onSaved,
}: EditVideoModalProps) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(video.title);
  const [description, setDescription] = useState(video.description || "");
  const [categoryId, setCategoryId] = useState(video.category_id || "");
  const [visibility, setVisibility] = useState(video.visibility);
  const [isPublished, setIsPublished] = useState(video.is_published);
  const [tagsInput, setTagsInput] = useState((video.tags || []).join(", "));
  const [membershipTypeIds, setMembershipTypeIds] = useState<string[]>([]);

  const { data: categories } = useQuery({
    queryKey: ["video-categories"],
    queryFn: () => videoApi.listCategories().then((r) => r.data.data),
  });

  const mutation = useMutation({
    mutationFn: () => {
      const tags = tagsInput
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      const data: Record<string, unknown> = {
        title,
        description: description || undefined,
        category_id: categoryId || undefined,
        visibility,
        is_published: isPublished,
        tags,
      };

      if (visibility === "specific_memberships" && membershipTypeIds.length > 0) {
        data.membership_type_ids = membershipTypeIds;
      }

      return videoApi.updateVideo(video.id, data as {
        title?: string;
        description?: string;
        category_id?: string;
        visibility?: string;
        is_published?: boolean;
        tags?: string[];
        membership_type_ids?: string[];
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      toast.success("Video updated");
      onSaved();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to update video");
    },
  });

  const canSubmit = title.trim().length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-lg rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Edit Video</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-6 py-4">
          <div>
            <Label htmlFor="video-title">Title</Label>
            <Input
              id="video-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Video title"
            />
          </div>

          <div>
            <Label htmlFor="video-desc">Description</Label>
            <textarea
              id="video-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="flex w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="Optional description..."
            />
          </div>

          <div>
            <Label>Category</Label>
            <select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">No category</option>
              {categories?.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <Label>Visibility</Label>
            <select
              value={visibility}
              onChange={(e) => setVisibility(e.target.value)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="public">Public</option>
              <option value="members_only">Members Only</option>
              <option value="specific_memberships">Specific Memberships</option>
              <option value="unlisted">Unlisted</option>
            </select>
          </div>

          {visibility === "specific_memberships" && (
            <div>
              <Label htmlFor="membership-ids">
                Membership Type IDs (comma-separated)
              </Label>
              <Input
                id="membership-ids"
                value={membershipTypeIds.join(", ")}
                onChange={(e) =>
                  setMembershipTypeIds(
                    e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean)
                  )
                }
                placeholder="Enter membership type IDs..."
              />
              <p className="mt-1 text-xs text-gray-400">
                Only members with these membership types can view this video.
              </p>
            </div>
          )}

          <div>
            <Label htmlFor="video-tags">Tags (comma-separated)</Label>
            <Input
              id="video-tags"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              placeholder="yoga, beginner, 30min..."
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="video-published"
              checked={isPublished}
              onChange={(e) => setIsPublished(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <Label htmlFor="video-published">Published</Label>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!canSubmit || mutation.isPending}
          >
            {mutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Save Changes
          </Button>
        </div>
      </div>
    </div>
  );
}
