"use client";

import { startTransition, useActionState, useEffect, useRef, useState } from "react";

import { submitReport } from "@/app/actions/field-reports";
import { Field, FormMessage, SelectField, SubmitButton, TextAreaField } from "@/components/form";
import { EVENT_TYPE_GROUPS } from "@/lib/event-types";
import { DHAKA_OFFSET, dhakaNowLocalInput, formatBytes } from "@/lib/format";
import type { ActionState } from "@/lib/types";

// Same limits as the backend; checked here first so nobody waits for a doomed upload.
const MAX_PHOTOS = 4;
const MAX_PHOTO_BYTES = 8 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];
const BD_LAT = [20.5, 26.7] as const;
const BD_LON = [88.0, 92.7] as const;

type Photo = { file: File; url: string };
type Locating =
  | { state: "idle" }
  | { state: "busy" }
  | { state: "done"; accuracy: number }
  | { state: "error"; message: string };

function geoErrorMessage(error: GeolocationPositionError): string {
  if (error.code === error.PERMISSION_DENIED)
    return "Location permission was refused. Allow it in the browser, or type the coordinates.";
  if (error.code === error.TIMEOUT)
    return "No GPS fix yet. Step outside or near a window and try again, or type the coordinates.";
  return "The phone could not find its location. Type the coordinates instead.";
}

export function ReportForm({
  clientReportId,
  defaultObservedAt,
}: {
  clientReportId: string;
  defaultObservedAt: string;
}) {
  // Controlled fields: nothing typed is lost if the send fails.
  const [text, setText] = useState("");
  const [eventType, setEventType] = useState("");
  const [placeName, setPlaceName] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [observedAt, setObservedAt] = useState(defaultObservedAt);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [locating, setLocating] = useState<Locating>({ state: "idle" });
  const [problem, setProblem] = useState<ActionState>();

  const [state, action, pending] = useActionState(submitReport, undefined);
  const fileInput = useRef<HTMLInputElement>(null);

  // Release preview images when the form goes away.
  const photosRef = useRef(photos);
  useEffect(() => {
    photosRef.current = photos;
  }, [photos]);
  useEffect(() => () => photosRef.current.forEach((p) => URL.revokeObjectURL(p.url)), []);

  function locate() {
    if (!window.isSecureContext || !("geolocation" in navigator)) {
      setLocating({
        state: "error",
        message:
          "This browser only shares location over HTTPS. Type the coordinates, or open CARCUX through its HTTPS address.",
      });
      return;
    }
    setLocating({ state: "busy" });
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLatitude(pos.coords.latitude.toFixed(6));
        setLongitude(pos.coords.longitude.toFixed(6));
        setAccuracy(Math.round(pos.coords.accuracy));
        setLocating({ state: "done", accuracy: Math.round(pos.coords.accuracy) });
      },
      (error) => setLocating({ state: "error", message: geoErrorMessage(error) }),
      { enableHighAccuracy: true, timeout: 20_000, maximumAge: 0 },
    );
  }

  // Typing coordinates by hand means the GPS accuracy no longer describes them.
  function typedCoordinate(setter: (v: string) => void, value: string) {
    setter(value);
    setAccuracy(null);
    if (locating.state === "done") setLocating({ state: "idle" });
  }

  function addPhotos(files: FileList | null) {
    if (!files) return;
    const added: Photo[] = [];
    const refused: string[] = [];
    for (const file of Array.from(files)) {
      if (!PHOTO_TYPES.includes(file.type))
        refused.push(`${file.name} is not a JPEG, PNG or WebP photo`);
      else if (file.size > MAX_PHOTO_BYTES) refused.push(`${file.name} is over 8 MB`);
      else if (photos.length + added.length >= MAX_PHOTOS)
        refused.push(`${file.name}: at most ${MAX_PHOTOS} photos`);
      else added.push({ file, url: URL.createObjectURL(file) });
    }
    setPhotos((current) => [...current, ...added]);
    setProblem(refused.length ? { ok: false, message: `${refused.join("; ")}.` } : undefined);
    if (fileInput.current) fileInput.current.value = ""; // allow picking the same file again
  }

  function removePhoto(index: number) {
    setPhotos((current) => {
      URL.revokeObjectURL(current[index].url);
      return current.filter((_, i) => i !== index);
    });
  }

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!latitude || !longitude || Number.isNaN(lat) || Number.isNaN(lon)) {
      setProblem({
        ok: false,
        message: "Add the location: use your location, or type the coordinates.",
      });
      return;
    }
    if (lat < BD_LAT[0] || lat > BD_LAT[1] || lon < BD_LON[0] || lon > BD_LON[1]) {
      setProblem({
        ok: false,
        message: "That location is outside Bangladesh. Check the coordinates.",
      });
      return;
    }
    setProblem(undefined);

    const body = new FormData();
    body.set("client_report_id", clientReportId);
    body.set("text", text.trim());
    body.set("latitude", String(lat));
    body.set("longitude", String(lon));
    body.set("observed_at", `${observedAt}:00${DHAKA_OFFSET}`);
    if (eventType) body.set("event_type", eventType);
    if (placeName.trim()) body.set("place_name", placeName.trim());
    if (accuracy !== null && accuracy > 0) body.set("location_accuracy_m", String(accuracy));
    for (const p of photos) body.append("photos", p.file, p.file.name);

    startTransition(() => action(body));
  }

  const message = problem ?? state;

  return (
    <form onSubmit={onSubmit} className="flex max-w-3xl flex-col gap-8" aria-busy={pending}>
      <fieldset className="flex flex-col gap-5">
        <legend className="display mb-4 text-2xl">What</legend>
        <TextAreaField
          label="What do you see?"
          name="text"
          required
          maxLength={4000}
          rows={4}
          placeholder="e.g. Knee-deep water at Mirpur 10 circle, rickshaws only, buses turned back."
          hint="Bangla, English or Banglish. Say what you saw yourself, and what you heard from others."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <SelectField
          label="Type of event"
          name="event_type"
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
        >
          <option value="">Not sure / other</option>
          {EVENT_TYPE_GROUPS.map((g) => (
            <optgroup key={g.family} label={g.family}>
              {g.types.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </optgroup>
          ))}
        </SelectField>
      </fieldset>

      <fieldset className="flex flex-col gap-5">
        <legend className="display mb-4 text-2xl">Where</legend>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
          <button
            type="button"
            onClick={locate}
            disabled={locating.state === "busy"}
            className="h-11 rounded-sm border border-steel px-4 text-bone transition-colors hover:bg-panel-2 disabled:cursor-wait disabled:opacity-60"
          >
            {locating.state === "busy" ? "Finding location…" : "Use my location"}
          </button>
          <p role="status" className="text-sm text-steel">
            {locating.state === "done" &&
              `Location found, accurate to about ${locating.accuracy} m.`}
            {locating.state === "error" && <span className="text-bone">{locating.message}</span>}
          </p>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Latitude"
            name="latitude"
            inputMode="decimal"
            placeholder="23.8069"
            value={latitude}
            onChange={(e) => typedCoordinate(setLatitude, e.target.value)}
          />
          <Field
            label="Longitude"
            name="longitude"
            inputMode="decimal"
            placeholder="90.3687"
            value={longitude}
            onChange={(e) => typedCoordinate(setLongitude, e.target.value)}
          />
        </div>
        <Field
          label="Place name"
          name="place_name"
          maxLength={200}
          placeholder="e.g. Mirpur 10 golchottor"
          hint="Optional, but it helps people who know the area."
          value={placeName}
          onChange={(e) => setPlaceName(e.target.value)}
        />
      </fieldset>

      <fieldset className="flex flex-col gap-5">
        <legend className="display mb-4 text-2xl">When</legend>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:gap-4">
          <div className="sm:w-72">
            <Field
              label="Seen at (Dhaka time)"
              name="observed_at"
              type="datetime-local"
              required
              value={observedAt}
              onChange={(e) => setObservedAt(e.target.value)}
            />
          </div>
          <button
            type="button"
            onClick={() => setObservedAt(dhakaNowLocalInput())}
            className="h-11 rounded-sm border border-line px-4 text-sm text-steel transition-colors hover:border-steel hover:text-bone"
          >
            Now
          </button>
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="display mb-4 text-2xl">Photos</legend>
        <p className="-mt-2 text-sm text-steel">
          Up to {MAX_PHOTOS}, 8 MB each. Take them now if you can: a photo used in another report is
          flagged.
        </p>
        {photos.length > 0 && (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {photos.map((p, i) => (
              <li key={p.url} className="flex flex-col gap-1.5">
                {/* Local preview of a file that has not been uploaded yet. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={p.url}
                  alt={`Photo ${i + 1} to send`}
                  className="aspect-square w-full rounded-sm border border-line object-cover"
                />
                <div className="flex items-center justify-between gap-2 text-xs text-steel">
                  <span>{formatBytes(p.file.size)}</span>
                  <button
                    type="button"
                    onClick={() => removePhoto(i)}
                    className="text-steel underline-offset-2 hover:text-bone hover:underline"
                  >
                    Remove<span className="sr-only"> photo {i + 1}</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {photos.length < MAX_PHOTOS && (
          <label className="inline-flex h-11 w-fit cursor-pointer items-center rounded-sm border border-steel px-4 text-bone transition-colors focus-within:outline-2 focus-within:outline-bone hover:bg-panel-2">
            {photos.length ? "Add another photo" : "Take or choose photos"}
            <input
              ref={fileInput}
              type="file"
              accept={PHOTO_TYPES.join(",")}
              multiple
              className="sr-only"
              onChange={(e) => addPhotos(e.target.files)}
            />
          </label>
        )}
      </fieldset>

      <div className="flex flex-col gap-4 border-t border-line pt-6 sm:flex-row sm:items-center">
        <SubmitButton pending={pending} pendingText="Sending…">
          Send report
        </SubmitButton>
        <FormMessage state={message} />
      </div>
    </form>
  );
}
