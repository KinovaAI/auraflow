"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Plus, Loader2, Mail, Phone, Search } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { InstructorFormModal } from "@/components/instructors/instructor-form-modal";
import { instructorsApi, type Instructor } from "@/lib/instructors-api";

export default function InstructorsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [search, setSearch] = useState("");

  const { data: instructors, isLoading } = useQuery({
    queryKey: ["instructors"],
    queryFn: () => instructorsApi.list().then((r) => r.data),
  });

  const filtered = instructors?.filter(
    (i) =>
      !search ||
      i.display_name.toLowerCase().includes(search.toLowerCase()) ||
      i.email?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Instructors</h1>
          <p className="text-sm text-gray-500">
            Manage your teaching staff and their availability
          </p>
        </div>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Instructor
        </Button>
      </div>

      {/* Search */}
      <div className="relative w-full sm:max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <Input
          placeholder="Search instructors..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      ) : !filtered?.length ? (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
          <p className="text-sm text-gray-500">
            {search ? "No instructors match your search" : "No instructors yet"}
          </p>
          {!search && (
            <Button
              variant="link"
              className="mt-2"
              onClick={() => setShowForm(true)}
            >
              Add your first instructor
            </Button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((instructor) => (
            <Card
              key={instructor.id}
              className="cursor-pointer transition-shadow hover:shadow-md"
              onClick={() =>
                router.push(`/dashboard/instructors/${instructor.id}`)
              }
            >
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <div
                    className="flex h-10 w-10 items-center justify-center rounded-full text-sm font-medium text-white"
                    style={{
                      backgroundColor: instructor.color || "#6366F1",
                    }}
                  >
                    {instructor.display_name
                      .split(" ")
                      .map((n) => n[0])
                      .join("")
                      .toUpperCase()
                      .slice(0, 2)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate font-medium text-gray-900">
                      {instructor.display_name}
                    </h3>
                    {instructor.specialties?.length ? (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {instructor.specialties.slice(0, 3).map((s) => (
                          <span
                            key={s}
                            className="inline-block rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    <div className="mt-2 space-y-1">
                      {instructor.email && (
                        <div className="flex items-center gap-1.5 text-xs text-gray-500">
                          <Mail className="h-3 w-3" />
                          <span className="truncate">{instructor.email}</span>
                        </div>
                      )}
                      {instructor.phone && (
                        <div className="flex items-center gap-1.5 text-xs text-gray-500">
                          <Phone className="h-3 w-3" />
                          {instructor.phone}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Form Modal */}
      {showForm && (
        <InstructorFormModal
          onClose={() => setShowForm(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["instructors"] });
            setShowForm(false);
            toast.success("Instructor added");
          }}
        />
      )}
    </div>
  );
}
