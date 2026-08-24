#define GLIB_DISABLE_DEPRECATION_WARNINGS 1

#include <gtk/gtk.h>
#include <math.h>

G_BEGIN_DECLS


typedef struct {
    gboolean is_running;
    guint32  _pad;
    guint64  last_frame_time;
    guint64  duration;
    gdouble  iteration;
    gdouble  iteration_count;
} GtkProgressTracker;

typedef struct _GtkCssGadget GtkCssGadget;
struct _GtkCssGadget { GObject parent; };

typedef struct _GtkStackChildInfo GtkStackChildInfo;
struct _GtkStackChildInfo {
    GtkWidget *widget;
    gchar     *name;
    gchar     *title;
    gchar     *icon_name;
    gboolean   needs_attention;
    GtkWidget *last_focus;
};


typedef struct {
    GList *children;
    GdkWindow *bin_window;
    GdkWindow *view_window;
    GtkStackChildInfo *visible_child;
    GtkCssGadget *gadget;
    gboolean hhomogeneous;
    gboolean vhomogeneous;
    GtkStackTransitionType transition_type;
    guint transition_duration;
    GtkStackChildInfo *last_visible_child;
    cairo_surface_t *last_visible_surface;
    GtkAllocation last_visible_surface_allocation;
    guint tick_id;
    GtkProgressTracker tracker;
    gboolean first_frame_skipped;
    gint last_visible_widget_width;
    gint last_visible_widget_height;
    gboolean interpolate_size;
    GtkStackTransitionType active_transition_type;
} GtkStackPrivate;


typedef struct {
    GtkRevealerTransitionType transition_type;
    guint transition_duration;
    GdkWindow *bin_window;
    GdkWindow *view_window;
    gdouble current_pos;
    gdouble source_pos;
    gdouble target_pos;
    guint tick_id;
    GtkProgressTracker tracker;
} GtkRevealerPrivate;

G_END_DECLS


static gdouble
inverse_ease_out_cubic(gdouble p)
{
    return cbrt(p - 1.0) + 1.0;
}


static GtkStackPrivate *
hacktk_stack_get_priv(GtkStack *stack)
{
    if (!GTK_IS_STACK(stack)) {
        g_error("hacktk: not a GtkStack!");
        return NULL;
    }
    return G_TYPE_INSTANCE_GET_PRIVATE(stack, GTK_TYPE_STACK, GtkStackPrivate);
}


static GtkRevealerPrivate *
hacktk_revealer_get_priv(GtkRevealer *revealer)
{
    if (!GTK_IS_REVEALER(revealer)) {
        g_error("hacktk: not a GtkRevealer!");
        return NULL;
    }
    return G_TYPE_INSTANCE_GET_PRIVATE(revealer, GTK_TYPE_REVEALER, GtkRevealerPrivate);
}


void
gtk_stack_begin_transition(GtkStack *stack)
{
    GtkStackPrivate *priv = hacktk_stack_get_priv(stack);
    if (!priv) return;

    if (priv->tick_id != 0) {
        gtk_widget_remove_tick_callback(GTK_WIDGET(stack), priv->tick_id);
        priv->tick_id = 0;
    }

    GtkProgressTracker *tracker = (GtkProgressTracker *)&priv->tracker;
    tracker->is_running = TRUE;
    tracker->iteration = 0.0;
    tracker->iteration_count = 1.0;
}

void
gtk_stack_set_timeline(GtkStack *stack, gdouble p, gint transition_type)
{
    GtkStackPrivate *priv = hacktk_stack_get_priv(stack);
    GtkWidget *widget = GTK_WIDGET(stack);
    if (!priv) return;
    if (priv->last_visible_child == NULL) return;

    if (priv->tick_id != 0) {
        gtk_widget_remove_tick_callback(widget, priv->tick_id);
        priv->tick_id = 0;
    }

    GtkProgressTracker *tracker = (GtkProgressTracker *)&priv->tracker;
    tracker->is_running = TRUE;
    tracker->iteration = inverse_ease_out_cubic(p);
    tracker->iteration_count = 1.0;

    GtkAllocation allocation;
    gtk_widget_get_allocation(widget, &allocation);

    if (priv->active_transition_type == GTK_STACK_TRANSITION_TYPE_SLIDE_RIGHT)
        gdk_window_move(priv->bin_window, (int)(allocation.width * -(1.0 - p)), 0);
    else if (priv->active_transition_type == GTK_STACK_TRANSITION_TYPE_SLIDE_LEFT)
        gdk_window_move(priv->bin_window, (int)(allocation.width * (1.0 - p)), 0);
    else if (priv->active_transition_type == GTK_STACK_TRANSITION_TYPE_SLIDE_DOWN)
        gdk_window_move(priv->bin_window, 0, (int)(allocation.height * -(1.0 - p)));
    else if (priv->active_transition_type == GTK_STACK_TRANSITION_TYPE_SLIDE_UP)
        gdk_window_move(priv->bin_window, 0, (int)(allocation.height * (1.0 - p)));

    gtk_widget_queue_draw(widget);

    if (!priv->vhomogeneous || !priv->hhomogeneous)
        gtk_widget_queue_resize(widget);
}

void
gtk_stack_end_transition(GtkStack *stack)
{
    GtkStackPrivate *priv = hacktk_stack_get_priv(stack);
    if (!priv) return;

    if (priv->last_visible_surface != NULL) {
        cairo_surface_destroy(priv->last_visible_surface);
        priv->last_visible_surface = NULL;
    }
    if (priv->last_visible_child != NULL) {
        gtk_widget_set_child_visible(priv->last_visible_child->widget, FALSE);
        priv->last_visible_child = NULL;
    }
    priv->active_transition_type = GTK_STACK_TRANSITION_TYPE_SLIDE_LEFT_RIGHT;
    GtkProgressTracker *tracker = (GtkProgressTracker *)&priv->tracker;
    tracker->is_running = FALSE;
}


GtkRevealerTransitionType
gtk_revealer_get_effective_transition(GtkRevealer *revealer)
{
    GtkRevealerPrivate *priv = hacktk_revealer_get_priv(revealer);

    if (gtk_widget_get_direction(GTK_WIDGET(revealer)) == GTK_TEXT_DIR_RTL) {
        if (priv->transition_type == GTK_REVEALER_TRANSITION_TYPE_SLIDE_LEFT)
            return GTK_REVEALER_TRANSITION_TYPE_SLIDE_RIGHT;
        else if (priv->transition_type == GTK_REVEALER_TRANSITION_TYPE_SLIDE_RIGHT)
            return GTK_REVEALER_TRANSITION_TYPE_SLIDE_LEFT;
    }
    return priv->transition_type;
}
void
gtk_revealer_set_timeline(GtkRevealer *revealer, gdouble pos)
{
    GtkRevealerPrivate *priv = hacktk_revealer_get_priv(revealer);
    GtkWidget *widget = GTK_WIDGET(revealer);
    if (!priv) return;
    if (!gtk_widget_get_realized(widget)) return;

    priv->current_pos = CLAMP(pos, 0.0, 1.0);
    priv->target_pos = 1.0;

    GtkWidget *child = gtk_bin_get_child(GTK_BIN(revealer));
    if (child != NULL)
        gtk_widget_set_child_visible(child, pos > 0.0);

    gtk_widget_queue_resize(widget);
}

void
gtk_revealer_fix_windows(GtkRevealer *revealer, gdouble pos)
{
    GtkRevealerPrivate *priv = hacktk_revealer_get_priv(revealer);
    GtkWidget *widget = GTK_WIDGET(revealer);
    if (!priv) return;
    if (!gtk_widget_get_realized(widget)) return;
    if (!priv->view_window) return;
    if (!priv->bin_window) return;

    if (pos <= 1.0) return;

    gint natural_height;
    gtk_widget_get_preferred_height(widget, NULL, &natural_height);

    GtkAllocation allocation;
    gtk_widget_get_allocation(widget, &allocation);

    gint current_height = (gint)round(natural_height * pos);
    gint overshoot = current_height - natural_height;

    GtkRevealerTransitionType effective = gtk_revealer_get_effective_transition(revealer);
    gboolean slide_up = (effective == GTK_REVEALER_TRANSITION_TYPE_SLIDE_UP);

    gint bin_offset = slide_up ? -overshoot : overshoot;

    gdk_window_move_resize(priv->view_window,
                           allocation.x, allocation.y,
                           allocation.width, current_height);

    gdk_window_move_resize(priv->bin_window,
                           0, bin_offset,
                           allocation.width, natural_height);
}

void
gtk_revealer_finish_transition(GtkRevealer *revealer)
{
    GtkRevealerPrivate *priv = hacktk_revealer_get_priv(revealer);
    if (!priv) return;
    priv->current_pos = 0.0;
    priv->target_pos = 0.0;
    gtk_widget_queue_resize(GTK_WIDGET(revealer));
}
