# AuraFlow Member Portal API Reference

Base URL: `https://api.your-domain.com/api/v1`

All portal endpoints are under `/api/v1/portal/`. Authentication is via JWT Bearer token. Tenant context is resolved automatically from the JWT `org_slug` claim.

---

## Authentication

### Login

```
POST /api/v1/auth/login/json
Content-Type: application/json
```

**Request:**
```json
{
  "email": "member@example.com",
  "password": "password123"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "abc123...",
  "token_type": "bearer",
  "expires_in": 14400
}
```

The `access_token` is a JWT valid for **4 hours** (14400 seconds). The JWT payload contains:
```json
{
  "sub": "user-uuid",
  "email": "member@example.com",
  "org_slug": "example-studio",
  "org_role": "member",
  "is_platform_admin": false,
  "exp": 1234567890
}
```

### Refresh Token

```
POST /api/v1/auth/refresh
Content-Type: application/json
```

**Request:**
```json
{
  "refresh_token": "abc123..."
}
```

**Response (200):** Same shape as login — returns new `access_token` and rotated `refresh_token`.

**Token cleanup:** Stale refresh tokens are automatically cleaned on each refresh call and by a daily cleanup task at 5 AM Pacific. If a network error occurs during an authenticated request, the client interceptor attempts a token refresh; if the refresh also fails, the user is redirected to the login page.

### Member Registration (Sign Up)

```
POST /api/v1/auth/member-register
Content-Type: application/json
```

**Request:**
```json
{
  "email": "newmember@example.com",
  "password": "securepass123",
  "first_name": "Jane",
  "last_name": "Doe",
  "org_slug": "example-studio"
}
```

- `password` must be at least 8 characters
- `org_slug` identifies which studio to register with (e.g. `"example-studio"`)
- If the email already exists as a user but isn't linked to this studio, it links them
- If an unlinked member record exists with the same email (e.g. imported from MindBody), it auto-links

**Response (201):** Same shape as login — returns tokens immediately (user is logged in).

**Errors:**
- `404` — Studio not found (`org_slug` invalid)
- `403` — Studio not accepting registrations
- `409` — Already registered with this studio

### Forgot Password

```
POST /api/v1/auth/forgot-password
Content-Type: application/json
```

**Request:**
```json
{
  "email": "member@example.com"
}
```

**Response (200):**
```json
{
  "message": "If an account exists, a password reset email has been sent."
}
```

### Reset Password

```
POST /api/v1/auth/reset-password
Content-Type: application/json
```

**Request:**
```json
{
  "token": "reset-token-from-email",
  "new_password": "newpassword123"
}
```

### Logout

```
POST /api/v1/auth/logout
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request:**
```json
{
  "refresh_token": "abc123..."
}
```

---

## Authenticated Requests

All `/portal/*` endpoints require:
```
Authorization: Bearer <access_token>
```

The JWT contains the `org_slug` claim so no additional tenant header is needed. All portal endpoints use `require_role("member")` which allows any role (member is the lowest in the hierarchy: owner > admin > instructor > front_desk > member).

### Post-Login Checks: Waiver and Payment Setup

After authenticating, call `GET /portal/me` and check these fields:

1. **Waiver check:** If the member has an unsigned waiver, the portal forces them to sign it on login before accessing any other page.
2. **Payment setup:** If `payment_setup_required` is `true`, the portal layout should redirect the member to the payment methods page (Stripe billing portal) before allowing navigation to any other page. The flag is cleared automatically when the member creates a new Stripe subscription.

---

## Profile

### Get My Profile

```
GET /api/v1/portal/me
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "id": "uuid",
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane@example.com",
  "phone": "+15551234567",
  "date_of_birth": "1990-05-15",
  "gender": "female",
  "emergency_contact_name": "John Doe",
  "emergency_contact_phone": "+15559876543",
  "photo_url": "https://...",
  "total_visits": 42,
  "member_number": "GR-001",
  "email_opt_in": true,
  "sms_opt_in": true,
  "payment_setup_required": false,
  "created_at": "2025-01-15T10:30:00"
}
```

- `payment_setup_required` — `true` if the member has been flagged to set up a payment method (e.g., after a failed payment or admin action). The portal frontend should redirect members with `payment_setup_required: true` to the payment methods page before allowing access to other pages.

**Errors:**
- `404` — Member profile not found (user account exists but no linked member record)

### Update My Profile

```
PUT /api/v1/portal/me
Authorization: Bearer <token>
Content-Type: application/json
```

**Request** (all fields optional, only send what changed):
```json
{
  "phone": "+15551234567",
  "emergency_contact_name": "John Doe",
  "emergency_contact_phone": "+15559876543",
  "email_opt_in": true,
  "sms_opt_in": false
}
```

Only these 5 fields can be updated by the member. Other fields are ignored.

**Response (200):** Full profile object (same shape as GET).

---

## Schedule

### Browse Upcoming Classes

```
GET /api/v1/portal/schedule
Authorization: Bearer <token>
```

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `start` | string (ISO 8601) | now | Start of date range |
| `end` | string (ISO 8601) | start + 14 days | End of date range |
| `class_type_id` | string (UUID) | — | Filter by class type |
| `instructor_id` | string (UUID) | — | Filter by instructor |
| `limit` | integer | 50 | Max results (max 200) |

**Response (200):**
```json
[
  {
    "id": "session-uuid",
    "title": "Morning Flow",
    "starts_at": "2026-03-02T09:00:00",
    "ends_at": "2026-03-02T10:00:00",
    "class_type_name": "Vinyasa Flow",
    "class_category": "yoga",
    "class_description": "A dynamic flow class...",
    "level": "all_levels",
    "instructor_name": "Sarah Johnson",
    "room_name": "Studio A",
    "spots_remaining": 5,
    "is_full": false,
    "waitlist_available": true,
    "is_virtual": false
  }
]
```

- `is_virtual` — `true` for Zoom/online classes, `false` for in-person. The Zoom join URL is NOT included here for security — only booked members get the link via the bookings endpoint.

---

## Bookings

### Get My Bookings

```
GET /api/v1/portal/bookings
Authorization: Bearer <token>
```

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `upcoming_only` | boolean | false | Only future confirmed/waitlisted bookings |
| `limit` | integer | 50 | Max results (max 200) |

**Response (200):**
```json
[
  {
    "id": "booking-uuid",
    "class_session_id": "session-uuid",
    "session_title": "Morning Flow",
    "class_type_name": "Vinyasa Flow",
    "class_category": "yoga",
    "instructor_name": "Sarah Johnson",
    "starts_at": "2026-03-02T09:00:00",
    "ends_at": "2026-03-02T10:00:00",
    "status": "confirmed",
    "booked_at": "2026-03-01T14:30:00",
    "waitlist_position": null,
    "is_virtual": true,
    "zoom_join_url": "https://zoom.us/j/123456789?pwd=abc123",
    "zoom_password": "abc123"
  }
]
```

- `is_virtual` — `true` for Zoom/online classes
- `zoom_join_url` — Zoom meeting link (only present for virtual classes with confirmed bookings)
- `zoom_password` — Zoom meeting password (may be `null`)
- The join URL should only be shown to the member near class time (e.g. 30 minutes before start through end)

**Booking statuses:** `confirmed`, `waitlisted`, `cancelled`, `attended`, `no_show`

### Book a Class

```
POST /api/v1/portal/bookings
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**
```json
{
  "session_id": "session-uuid",
  "membership_id": "membership-uuid"
}
```

- `membership_id` is optional — if provided, deducts a class from that membership (for class packs)
- If the class is full, the member is automatically added to the waitlist

**Response (201):** Booking object (same shape as above).

**Errors:**
- `400` — "You are already booked for this class"
- `400` — "Member profile not found"
- `400` — Various booking validation errors (class cancelled, no spots, etc.)

### Cancel a Booking

```
DELETE /api/v1/portal/bookings/{booking_id}
Authorization: Bearer <token>
```

**Response:** `204 No Content`

**Class pack credit restoration:** If the booking used a class pack credit and the cancellation is not late (per studio policy), the credit is automatically restored to the member's pack.

**Errors:**
- `403` — "Cannot cancel another member's booking"
- `400` — "Booking is already cancelled/attended/no_show"
- `404` — "Booking not found"

---

## Memberships

### Get My Memberships

```
GET /api/v1/portal/memberships
Authorization: Bearer <token>
```

Returns the member's active and frozen memberships.

**Response (200):**
```json
[
  {
    "id": "membership-uuid",
    "type_name": "Unlimited Monthly",
    "membership_type": "unlimited",
    "status": "active",
    "starts_at": "2026-01-01T00:00:00",
    "ends_at": "2026-04-01T00:00:00",
    "classes_remaining": null,
    "auto_renew": true,
    "price_cents": 14900
  }
]
```

**Membership statuses:** `active`, `frozen`
**Membership types:** `unlimited`, `class_pack`, `intro_offer`, `day_pass`, `single_class`

### Get Available Membership Types

```
GET /api/v1/portal/membership-types
Authorization: Bearer <token>
```

Returns publicly available plans the member can purchase.

**Response (200):**
```json
[
  {
    "id": "type-uuid",
    "name": "Unlimited Monthly",
    "description": "Unlimited classes every month",
    "type": "unlimited",
    "class_count": null,
    "price_cents": 14900,
    "billing_period": "monthly",
    "duration_days": null,
    "is_founding_rate": true,
    "trial_days": 7,
    "freeze_allowed": true,
    "is_public": true
  },
  {
    "id": "type-uuid-2",
    "name": "10-Class Pack",
    "description": "Use at your own pace",
    "type": "class_pack",
    "class_count": 10,
    "price_cents": 12000,
    "billing_period": null,
    "duration_days": 90,
    "is_founding_rate": false,
    "trial_days": 0,
    "freeze_allowed": false,
    "is_public": true
  }
]
```

**Billing periods:** `monthly`, `annual`, `yearly`, `weekly`, or `null` for one-time purchases.

---

## Payments & Checkout

### Create Checkout Session (Purchase a Membership)

```
POST /api/v1/portal/checkout
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**
```json
{
  "membership_type_id": "type-uuid",
  "success_url": "https://yoursite.com/memberships?success=1",
  "cancel_url": "https://yoursite.com/memberships?cancelled=1"
}
```

- The backend auto-resolves the member from the JWT (no need to pass `member_id`)
- Creates a Stripe Checkout Session (subscription mode for recurring, payment mode for one-time)
- For recurring memberships with `trial_days > 0`, a free trial is included

**Response (200):**
```json
{
  "data": {
    "url": "https://checkout.stripe.com/c/pay/cs_live_...",
    "session_id": "cs_live_..."
  }
}
```

Redirect the user to `data.url` to complete payment on Stripe's hosted checkout page.

**After checkout completes:**
1. Stripe sends a `checkout.session.completed` webhook to the API
2. The webhook handler auto-creates the member's membership record
3. A transaction record is created
4. The member is redirected to your `success_url`

**Errors:**
- `404` — Member profile not found
- `400` — Various Stripe/validation errors (invalid type, Stripe not configured, etc.)

### Get Payment History

```
GET /api/v1/portal/transactions
Authorization: Bearer <token>
```

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | integer | 50 | Max results (max 200) |

**Response (200):**
```json
[
  {
    "id": "transaction-uuid",
    "amount_cents": 14900,
    "type": "membership_purchase",
    "status": "completed",
    "description": "Unlimited Monthly membership",
    "created_at": "2026-03-01T14:30:00"
  }
]
```

**Transaction statuses:** `pending`, `completed`, `failed`, `refunded`, `partially_refunded`

### Open Stripe Billing Portal

```
POST /api/v1/portal/billing-portal
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**
```json
{
  "return_url": "https://yoursite.com/memberships"
}
```

Opens Stripe's hosted Customer Portal where members can:
- Update payment method
- View invoices
- Cancel subscriptions

**Response (200):**
```json
{
  "data": {
    "url": "https://billing.stripe.com/p/session/..."
  }
}
```

Redirect the user to `data.url`.

**Errors:**
- `404` — Member profile not found
- `400` — No Stripe customer found for this member

---

## AI Suggestions

### Get Personalized Class Suggestions

```
GET /api/v1/portal/suggestions
Authorization: Bearer <token>
```

Returns AI-powered class recommendations based on the member's booking history. Uses the member's last 20 attended classes to match preferences against the next 7 days of scheduled classes.

**Response (200):**
```json
[
  {
    "session_id": "session-uuid",
    "title": "Vinyasa Flow",
    "starts_at": "2026-03-02T09:00:00",
    "instructor_name": "Sarah Johnson",
    "reason": "Based on your love of flow classes, this morning session with your favorite instructor is a great fit."
  }
]
```

Returns up to 3 suggestions. Returns empty array `[]` if the member has no booking history or no upcoming classes are scheduled.

---

## Workshops & Events

### Browse Workshops

```
GET /api/v1/portal/workshops
Authorization: Bearer <token>
```

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | string | — | Filter: `workshop`, `course`, `teacher_training`, `retreat` |

**Response (200):**
```json
[
  {
    "id": "course-uuid",
    "title": "200-Hour Yoga Teacher Training",
    "description": "Comprehensive yoga teacher certification program...",
    "type": "teacher_training",
    "instructor_name": "Sarah Johnson",
    "price_cents": 250000,
    "early_bird_price_cents": 200000,
    "early_bird_deadline": "2026-03-15T00:00:00",
    "is_early_bird_active": true,
    "capacity": 20,
    "enrolled_count": 12,
    "spots_remaining": 8,
    "location": "Studio A",
    "is_virtual": false,
    "image_url": "https://...",
    "prerequisites": "6 months yoga experience",
    "starts_at": "2026-04-01T09:00:00",
    "ends_at": "2026-06-30T17:00:00"
  }
]
```

**Course types:** `workshop`, `course`, `teacher_training`, `retreat`

### Get Workshop Detail

```
GET /api/v1/portal/workshops/{course_id}
Authorization: Bearer <token>
```

Returns the workshop with its session schedule.

**Response (200):**
```json
{
  "id": "course-uuid",
  "title": "200-Hour Yoga Teacher Training",
  "type": "teacher_training",
  "instructor_name": "Sarah Johnson",
  "price_cents": 250000,
  "early_bird_price_cents": 200000,
  "early_bird_deadline": "2026-03-15T00:00:00",
  "is_early_bird_active": true,
  "capacity": 20,
  "enrolled_count": 12,
  "spots_remaining": 8,
  "starts_at": "2026-04-01T09:00:00",
  "ends_at": "2026-06-30T17:00:00",
  "sessions": [
    {
      "id": "session-uuid",
      "title": "Anatomy & Alignment",
      "session_number": 1,
      "starts_at": "2026-04-01T09:00:00",
      "ends_at": "2026-04-01T17:00:00",
      "location": "Studio A",
      "is_virtual": false
    },
    {
      "id": "session-uuid-2",
      "title": "Teaching Methodology",
      "session_number": 2,
      "starts_at": "2026-04-08T09:00:00",
      "ends_at": "2026-04-08T17:00:00",
      "location": "Studio A",
      "is_virtual": false
    }
  ]
}
```

### Get My Enrollments

```
GET /api/v1/portal/my-enrollments
Authorization: Bearer <token>
```

Returns the member's workshop/course enrollments.

**Response (200):**
```json
[
  {
    "id": "enrollment-uuid",
    "course_id": "course-uuid",
    "course_title": "200-Hour Yoga Teacher Training",
    "course_type": "teacher_training",
    "status": "enrolled",
    "paid_price_cents": 200000,
    "enrolled_at": "2026-03-01T14:30:00",
    "starts_at": "2026-04-01T09:00:00",
    "ends_at": "2026-06-30T17:00:00",
    "instructor_name": "Sarah Johnson",
    "is_virtual": false
  }
]
```

**Enrollment statuses:** `enrolled`, `withdrawn`, `completed`

### Enroll in a Workshop

```
POST /api/v1/portal/workshops/{course_id}/enroll
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**
```json
{
  "success_url": "https://yoursite.com/workshops?enrolled=1",
  "cancel_url": "https://yoursite.com/workshops?cancelled=1"
}
```

- **Free workshops** (`price_cents == 0`): Enrolls directly, returns `{"data": {"enrolled": true, "enrollment_id": "uuid"}}`
- **Paid workshops**: Creates a Stripe Checkout session, returns `{"data": {"url": "https://checkout.stripe.com/...", "session_id": "cs_..."}}`
- Early-bird pricing is applied automatically if the deadline hasn't passed

**Response (200) — free:**
```json
{
  "data": {
    "enrolled": true,
    "enrollment_id": "enrollment-uuid"
  }
}
```

**Response (200) — paid:**
```json
{
  "data": {
    "url": "https://checkout.stripe.com/c/pay/cs_live_...",
    "session_id": "cs_live_..."
  }
}
```

Redirect the user to `data.url`. After payment, the webhook auto-enrolls the member.

**Errors:**
- `404` — Workshop not found
- `400` — "Course is at capacity", "Member is already enrolled", etc.

### Withdraw from a Workshop

```
DELETE /api/v1/portal/workshops/enrollments/{enrollment_id}
Authorization: Bearer <token>
```

**Response:** `204 No Content`

**Errors:**
- `403` — "Cannot withdraw another member's enrollment"
- `404` — "Enrollment not found"

---

## Private Lessons

### Browse Instructors

```
GET /api/v1/portal/private-lessons/instructors
Authorization: Bearer <token>
```

Returns instructors who offer publicly-visible private services.

**Response (200):**
```json
[
  {
    "id": "instructor-uuid",
    "display_name": "Sarah Johnson",
    "bio": "Certified yoga instructor with 10 years of experience...",
    "photo_url": "https://...",
    "specialties": ["Vinyasa", "Yin", "Prenatal"],
    "certifications": ["RYT-500", "RPYT"]
  }
]
```

### Get Instructor's Services

```
GET /api/v1/portal/private-lessons/instructors/{instructor_id}/services
Authorization: Bearer <token>
```

**Response (200):**
```json
[
  {
    "id": "service-uuid",
    "name": "Private Yoga Session",
    "description": "One-on-one personalized yoga session",
    "duration_minutes": 60,
    "price_cents": 8500,
    "is_virtual": false
  },
  {
    "id": "service-uuid-2",
    "name": "Virtual Meditation Session",
    "description": "Guided meditation via Zoom",
    "duration_minutes": 30,
    "price_cents": 4500,
    "is_virtual": true
  }
]
```

### Get Available Time Slots

```
GET /api/v1/portal/private-lessons/slots
Authorization: Bearer <token>
```

**Query Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `instructor_id` | string (UUID) | Yes | Instructor ID |
| `service_id` | string (UUID) | Yes | Service ID |
| `date` | string (YYYY-MM-DD) | Yes | Target date |

Returns 15-minute interval slots based on instructor availability, minus blocked times and existing bookings (with buffer time).

**Response (200):**
```json
[
  {
    "start_time": "09:00:00",
    "end_time": "10:00:00",
    "duration_minutes": 60
  },
  {
    "start_time": "09:15:00",
    "end_time": "10:15:00",
    "duration_minutes": 60
  },
  {
    "start_time": "10:30:00",
    "end_time": "11:30:00",
    "duration_minutes": 60
  }
]
```

Times are in `HH:MM:SS` format (local to the studio).

### Book a Private Session

```
POST /api/v1/portal/private-lessons/book
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**
```json
{
  "instructor_id": "instructor-uuid",
  "private_service_id": "service-uuid",
  "starts_at": "2026-03-05T09:00:00",
  "intake_notes": "Working on hip flexibility",
  "success_url": "https://yoursite.com/private-lessons?booked=1",
  "cancel_url": "https://yoursite.com/private-lessons?cancelled=1"
}
```

- `starts_at` — ISO datetime combining the selected date and slot start time (e.g. `"2026-03-05T09:00:00"`)
- `intake_notes` — Optional notes for the instructor
- The booking is created in `pending` status immediately to reserve the time slot
- **Free sessions** (`price_cents == 0`): Returns `{"data": {"booked": true, "booking_id": "uuid"}}`
- **Paid sessions**: Creates Stripe Checkout, returns `{"data": {"url": "...", "session_id": "..."}}`

**Response (200) — free:**
```json
{
  "data": {
    "booked": true,
    "booking_id": "booking-uuid"
  }
}
```

**Response (200) — paid:**
```json
{
  "data": {
    "url": "https://checkout.stripe.com/c/pay/cs_live_...",
    "session_id": "cs_live_..."
  }
}
```

After payment, the webhook confirms the booking (`pending` → `confirmed`).

**Errors:**
- `404` — Service not found
- `400` — "Time slot conflicts with an existing booking"
- `400` — "Maximum bookings per day reached for this service"

### Get My Private Bookings

```
GET /api/v1/portal/private-lessons/my-bookings
Authorization: Bearer <token>
```

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `upcoming_only` | boolean | false | Only future pending/confirmed bookings |

**Response (200):**
```json
[
  {
    "id": "booking-uuid",
    "starts_at": "2026-03-05T09:00:00",
    "ends_at": "2026-03-05T10:00:00",
    "status": "confirmed",
    "is_virtual": false,
    "zoom_join_url": null,
    "service_name": "Private Yoga Session",
    "duration_minutes": 60,
    "instructor_name": "Sarah Johnson",
    "instructor_photo": "https://...",
    "price_cents": 8500,
    "payment_status": "paid",
    "payment_url": null,
    "created_at": "2026-03-01T14:30:00"
  }
]
```

**Booking statuses:** `pending`, `confirmed`, `cancelled`, `completed`, `no_show`

**Payment statuses:** `unpaid`, `paid` -- tracked independently from booking status. A session can be confirmed but unpaid.

- `zoom_join_url` — Present for virtual sessions only (after booking is confirmed)
- `payment_status` — Whether the member has paid for this session
- `payment_url` — Stripe payment link for unpaid sessions. `null` once paid. Display this as a "Pay Now" button for unpaid bookings.

### Cancel a Private Booking

```
DELETE /api/v1/portal/private-lessons/bookings/{booking_id}
Authorization: Bearer <token>
```

**Response:** `204 No Content`

**Errors:**
- `403` — "Cannot cancel another member's booking"
- `400` — "Booking is already cancelled/completed/no_show"
- `404` — "Booking not found"

---

## Video On-Demand Library

Members with **online** or **all-access** memberships can browse and watch on-demand video content. Use the `has_video_access` field from the user profile to determine whether to show video features in your UI.

### Check Video Access

```
GET /api/v1/users/me
Authorization: Bearer <token>
```

The response includes a `has_video_access` boolean:
```json
{
  "id": "user-uuid",
  "email": "member@example.com",
  "has_video_access": true,
  ...
}
```

- `true` for members with an active membership where `access_scope` is `"online"` or `"all_access"`
- `false` for members with only `"in_studio"` memberships
- Always `true` for staff/admin/owner roles

Use this field to conditionally show or hide the video section in your website navigation.

### Get Video Categories

```
GET /api/v1/video/categories
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "data": [
    {
      "id": "category-uuid",
      "name": "Yoga Flows",
      "description": "Vinyasa and flow-style classes",
      "slug": "yoga-flows",
      "sort_order": 1,
      "is_active": true,
      "video_count": 12
    }
  ]
}
```

Use categories to build filter tabs/pills in your video library UI.

### Browse Videos

```
GET /api/v1/video/browse
Authorization: Bearer <token>
```

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `category_id` | string (UUID) | — | Filter by category |
| `limit` | integer | 50 | Max results (max 200) |
| `offset` | integer | 0 | Pagination offset |

Returns only videos the member has access to (filtered automatically based on their active memberships).

**Response (200):**
```json
{
  "data": [
    {
      "id": "video-uuid",
      "source": "youtube",
      "title": "Morning Vinyasa Flow",
      "description": "A 45-minute energizing flow class...",
      "thumbnail_url": "https://img.youtube.com/vi/abc123/maxresdefault.jpg",
      "duration_seconds": 2700,
      "category_id": "category-uuid",
      "category_name": "Yoga Flows",
      "visibility": "all_members",
      "is_published": true,
      "tags": ["yoga", "vinyasa", "morning"],
      "youtube_video_id": "abc123",
      "mux_playback_id": null,
      "created_at": "2026-02-15T10:00:00",
      "updated_at": "2026-02-15T10:00:00"
    }
  ]
}
```

**Video sources:** `youtube`, `mux`, `zoom_recording`, `manual`

**Visibility types:** `all_members` (all members see it), `specific_memberships` (only members with linked membership types)

### Get Single Video

```
GET /api/v1/video/browse/{video_id}
Authorization: Bearer <token>
```

Returns full video details if the member has access. Use the `source` field to determine how to embed the player.

**Response (200):**
```json
{
  "data": {
    "id": "video-uuid",
    "source": "youtube",
    "title": "Morning Vinyasa Flow",
    "description": "A 45-minute energizing flow class...",
    "thumbnail_url": "https://img.youtube.com/vi/abc123/maxresdefault.jpg",
    "duration_seconds": 2700,
    "category_name": "Yoga Flows",
    "youtube_video_id": "abc123",
    "mux_playback_id": null,
    "tags": ["yoga", "vinyasa"]
  }
}
```

**Errors:**
- `404` — Video not found or member doesn't have access

### Embedding the Video Player

Use the `source` field to determine how to render the video:

**YouTube videos** (`source == "youtube"`):
```html
<iframe
  src="https://www.youtube-nocookie.com/embed/{youtube_video_id}?rel=0"
  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
  allowfullscreen
></iframe>
```

**Mux videos** (`source == "mux"`):
```html
<!-- Option 1: HLS stream (use hls.js for non-Safari browsers) -->
<video src="https://stream.mux.com/{mux_playback_id}.m3u8" controls></video>

<!-- Thumbnail/poster image -->
<img src="https://image.mux.com/{mux_playback_id}/thumbnail.webp?time=0" />
```

### Record a Video View (Optional)

```
POST /api/v1/video/browse/{video_id}/view
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**
```json
{
  "watched_seconds": 120,
  "completed": false
}
```

**Response (200):**
```json
{
  "data": {
    "recorded": true
  }
}
```

Call this when the member finishes watching or navigates away. Used for analytics and "continue watching" features.

---

## Public API (No Auth Required)

These endpoints are publicly accessible and do not require authentication.

### Get Studio Schedule (JSON)

```
GET /api/v1/public/{slug}/schedule
```

Returns the upcoming class schedule for the specified studio as JSON. No authentication required. Intended for external integrations, widgets, and API consumers.

### Get Studio Schedule (HTML)

```
GET /api/v1/public/{slug}/schedule.html
```

Returns an HTML schedule page for the specified studio. Designed for embedding in ClassPass and other external platforms.

### API Key Scopes

API keys can be created in the studio dashboard under **Settings > Integrations > API Keys**. Each key has a **granular scope selector** allowing fine-grained control over which endpoints the key can access.

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Human-readable error message"
}
```

**Common HTTP status codes:**
| Code | Meaning |
|------|---------|
| `400` | Bad request / validation error |
| `401` | Not authenticated (missing/expired token) |
| `403` | Forbidden (insufficient role or wrong member) |
| `404` | Resource not found |
| `409` | Conflict (duplicate registration) |
| `422` | Validation error (Pydantic) |

Pydantic validation errors (422) use this format:
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

---

## TypeScript Types

```typescript
// Auth
interface LoginRequest {
  email: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

interface MemberRegisterRequest {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  org_slug: string;
}

// Profile
interface PortalProfile {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  date_of_birth?: string;
  gender?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  photo_url?: string;
  total_visits: number;
  member_number?: string;
  email_opt_in: boolean;
  sms_opt_in: boolean;
  payment_setup_required: boolean;
  created_at?: string;
}

interface PortalProfileUpdate {
  phone?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  email_opt_in?: boolean;
  sms_opt_in?: boolean;
}

// Schedule
interface PortalSession {
  id: string;
  title?: string;
  starts_at: string;
  ends_at?: string;
  class_type_name?: string;
  class_category?: string;
  class_description?: string;
  level?: string;
  instructor_name?: string;
  room_name?: string;
  spots_remaining: number;
  is_full: boolean;
  waitlist_available: boolean;
  is_virtual?: boolean;
}

// Bookings
interface PortalBooking {
  id: string;
  class_session_id: string;
  session_title?: string;
  class_type_name?: string;
  class_category?: string;
  instructor_name?: string;
  starts_at?: string;
  ends_at?: string;
  status: string;
  booked_at?: string;
  waitlist_position?: number;
  is_virtual?: boolean;
  zoom_join_url?: string;
  zoom_password?: string;
}

// Memberships
interface PortalMembership {
  id: string;
  type_name: string;
  membership_type?: string;
  status: string;
  starts_at?: string;
  ends_at?: string;
  classes_remaining?: number;
  auto_renew?: boolean;
  price_cents?: number;
}

interface PortalMembershipType {
  id: string;
  name: string;
  description?: string;
  type: string;
  class_count?: number;
  price_cents: number;
  billing_period?: string;
  duration_days?: number;
  is_founding_rate: boolean;
  trial_days: number;
  freeze_allowed: boolean;
  is_public: boolean;
}

// Payments
interface PortalTransaction {
  id: string;
  amount_cents: number;
  type: string;
  status: string;
  description?: string;
  created_at?: string;
}

// Video Library
interface Video {
  id: string;
  source: "youtube" | "mux" | "zoom_recording" | "manual";
  title: string;
  description?: string;
  thumbnail_url?: string;
  duration_seconds?: number;
  category_id?: string;
  category_name?: string;
  visibility: string;
  is_published: boolean;
  tags: string[];
  youtube_video_id?: string;
  mux_playback_id?: string;
  created_at: string;
  updated_at?: string;
}

interface VideoCategory {
  id: string;
  name: string;
  description?: string;
  slug: string;
  sort_order: number;
  is_active: boolean;
  video_count: number;
}

// AI Suggestions
interface PortalSuggestion {
  session_id: string;
  title: string;
  starts_at: string;
  instructor_name?: string;
  reason: string;
}
```

---

## Quick Start: API Client Example

```typescript
const API_BASE = "https://api.your-domain.com/api/v1";

// Login
const loginRes = await fetch(`${API_BASE}/auth/login/json`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "member@example.com", password: "pass123" }),
});
const { access_token, refresh_token } = await loginRes.json();

// Authenticated request helper
const authFetch = (path: string, options?: RequestInit) =>
  fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${access_token}`,
      ...options?.headers,
    },
  }).then((r) => r.json());

// Get profile
const profile = await authFetch("/portal/me");

// Browse schedule
const classes = await authFetch("/portal/schedule?limit=20");

// Book a class
const booking = await authFetch("/portal/bookings", {
  method: "POST",
  body: JSON.stringify({ session_id: "session-uuid" }),
});

// Get memberships
const memberships = await authFetch("/portal/memberships");

// Purchase a membership
const checkout = await authFetch("/portal/checkout", {
  method: "POST",
  body: JSON.stringify({
    membership_type_id: "type-uuid",
    success_url: "https://yoursite.com/success",
    cancel_url: "https://yoursite.com/cancel",
  }),
});
// Redirect user to checkout.data.url

// Get payment history
const transactions = await authFetch("/portal/transactions");

// Get AI suggestions
const suggestions = await authFetch("/portal/suggestions");

// Check if member has video access
const user = await authFetch("/users/me");
if (user.has_video_access) {
  // Get video categories
  const categories = await authFetch("/video/categories");

  // Browse videos (filtered by member's membership access)
  const videos = await authFetch("/video/browse?limit=50");

  // Browse by category
  const yogaVideos = await authFetch("/video/browse?category_id=category-uuid");

  // Get single video for playback
  const video = await authFetch("/video/browse/video-uuid");
  // Embed using video.data.youtube_video_id or video.data.mux_playback_id

  // Record a view when member watches
  await authFetch("/video/browse/video-uuid/view", {
    method: "POST",
    body: JSON.stringify({ watched_seconds: 300, completed: true }),
  });
}
```

---

## Studio Configuration

For your studio integration:
- **org_slug:** `example-studio`
- **API Base:** `https://api.your-domain.com/api/v1`
- All dates are ISO 8601 format
- All monetary amounts are in **cents** (e.g. `14900` = $149.00)
- Stripe Checkout handles PCI compliance — your frontend never touches card data
