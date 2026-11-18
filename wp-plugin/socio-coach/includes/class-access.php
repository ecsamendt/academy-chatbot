<?php
/**
 * Works out which MemberPress memberships can see a MemberPress Courses lesson,
 * so the coach never shows a lesson's content to members without access.
 *
 * VERIFY ON STAGING: MemberPress internals differ between versions. Every call
 * below is guarded, and the result can be overridden with the
 * `socio_coach_lesson_access` filter. When nothing can be determined, the lesson
 * is marked staff-only (fail closed), never public.
 */

if (!defined('ABSPATH')) {
    exit;
}

class Socio_Coach_Access
{
    /** Course post ID for a lesson (lesson -> section -> course). */
    public static function course_id($lesson_id)
    {
        // MemberPress Courses model, when available.
        if (class_exists('\\memberpress\\courses\\models\\Lesson')) {
            try {
                $lesson = new \memberpress\courses\models\Lesson($lesson_id);
                if (method_exists($lesson, 'course')) {
                    $course = $lesson->course();
                    if ($course && !empty($course->ID)) {
                        return (int) $course->ID;
                    }
                }
            } catch (\Throwable $e) {
                // fall through to the database lookup
            }
        }
        global $wpdb;
        $section_id = (int) get_post_meta($lesson_id, '_mpcs_lesson_section_id', true);
        if ($section_id) {
            $table = $wpdb->prefix . 'mpcs_sections';
            $course_id = $wpdb->get_var($wpdb->prepare("SELECT course_id FROM {$table} WHERE id = %d", $section_id));
            if ($course_id) {
                return (int) $course_id;
            }
        }
        return 0;
    }

    public static function section_title($lesson_id)
    {
        global $wpdb;
        $section_id = (int) get_post_meta($lesson_id, '_mpcs_lesson_section_id', true);
        if (!$section_id) {
            return null;
        }
        $table = $wpdb->prefix . 'mpcs_sections';
        $title = $wpdb->get_var($wpdb->prepare("SELECT title FROM {$table} WHERE id = %d", $section_id));
        return $title ? (string) $title : null;
    }

    /** Membership IDs named by MemberPress rules that protect a post. null = unknown. */
    private static function rule_memberships($post_id, &$protected)
    {
        if (!class_exists('MeprRule') || !method_exists('MeprRule', 'get_rules')) {
            return null;
        }
        $post = get_post($post_id);
        if (!$post) {
            return array();
        }
        $rules = (array) MeprRule::get_rules($post);
        if (!$rules) {
            return array();
        }
        $protected = true;
        $ids = array();
        foreach ($rules as $rule) {
            if (method_exists($rule, 'get_access_list')) {
                $list = (array) $rule->get_access_list();
                if (!empty($list['membership'])) {
                    $ids = array_merge($ids, array_map('intval', (array) $list['membership']));
                }
            } elseif (!empty($rule->access_conditions)) {
                foreach ((array) $rule->access_conditions as $cond) {
                    if (isset($cond->access_type) && $cond->access_type === 'membership') {
                        $ids[] = (int) $cond->access_condition;
                    }
                }
            }
        }
        return array_values(array_unique(array_filter($ids)));
    }

    /**
     * @return array{is_public: bool, membership_ids: int[], plan_label: ?string}
     */
    public static function for_lesson($lesson_id)
    {
        $course_id = self::course_id($lesson_id);
        $protected = false;
        $unknown = false;
        $ids = array();
        foreach (array_filter(array($lesson_id, $course_id)) as $pid) {
            $found = self::rule_memberships($pid, $protected);
            if ($found === null) {
                $unknown = true;
                break;
            }
            $ids = array_merge($ids, $found);
        }
        $ids = array_values(array_unique($ids));

        $result = array(
            // No MemberPress = can't tell = staff only. No rules at all = open to every member.
            'is_public'      => !$unknown && !$protected,
            'membership_ids' => $ids,
            'plan_label'     => self::plan_label($ids),
        );
        return apply_filters('socio_coach_lesson_access', $result, $lesson_id, $course_id);
    }

    /** "Plan Pro o Plan Elite", from membership titles, for upgrade prompts. */
    public static function plan_label($membership_ids)
    {
        $names = array();
        foreach ($membership_ids as $id) {
            $title = get_the_title($id);
            if ($title) {
                $names[] = $title;
            }
        }
        return $names ? implode(' o ', $names) : null;
    }
}
