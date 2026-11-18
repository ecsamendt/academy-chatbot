<?php
/**
 * REST routes under /wp-json/socio-coach/v1
 *   GET /lessons, /lessons/<id>   lesson feed for the coach service (X-Socio-Ingest-Secret)
 *   GET /token                    fresh member token for the chat window (logged-in, wp_rest nonce)
 */

if (!defined('ABSPATH')) {
    exit;
}

class Socio_Coach_Rest
{
    const NS = 'socio-coach/v1';

    public static function init()
    {
        add_action('rest_api_init', array(__CLASS__, 'routes'));
    }

    public static function routes()
    {
        register_rest_route(self::NS, '/lessons', array(
            'methods'             => 'GET',
            'callback'            => array(__CLASS__, 'list_lessons'),
            'permission_callback' => array(__CLASS__, 'ingest_allowed'),
            'args'                => array(
                'page'     => array('type' => 'integer', 'default' => 1, 'minimum' => 1),
                'per_page' => array('type' => 'integer', 'default' => 50, 'minimum' => 1, 'maximum' => 100),
            ),
        ));
        register_rest_route(self::NS, '/lessons/(?P<id>\d+)', array(
            'methods'             => 'GET',
            'callback'            => array(__CLASS__, 'get_lesson'),
            'permission_callback' => array(__CLASS__, 'ingest_allowed'),
        ));
        register_rest_route(self::NS, '/token', array(
            'methods'             => 'GET',
            'callback'            => array(__CLASS__, 'token'),
            'permission_callback' => 'is_user_logged_in',
        ));
    }

    public static function ingest_allowed(WP_REST_Request $request)
    {
        $expected = Socio_Coach_Settings::get('ingest_secret');
        $given = (string) $request->get_header('x-socio-ingest-secret');
        return $expected !== '' && hash_equals($expected, $given);
    }

    public static function lesson_payload(WP_Post $post)
    {
        $course_id = Socio_Coach_Access::course_id($post->ID);
        $access = Socio_Coach_Access::for_lesson($post->ID);
        // Optional override when a lesson embeds more than one video: custom field
        // "socio_coach_vimeo_id" with the ID (or comma-separated IDs) to index.
        $override = trim((string) get_post_meta($post->ID, 'socio_coach_vimeo_id', true));
        return array(
            'id'             => $post->ID,
            'title'          => html_entity_decode(get_the_title($post), ENT_QUOTES, 'UTF-8'),
            'url'            => get_permalink($post),
            'status'         => $post->post_status,
            'modified'       => $post->post_modified_gmt,
            'course_id'      => $course_id ?: null,
            'course_title'   => $course_id ? html_entity_decode(get_the_title($course_id), ENT_QUOTES, 'UTF-8') : null,
            'section_title'  => Socio_Coach_Access::section_title($post->ID),
            'content'        => $post->post_content,
            'vimeo_ids'      => $override !== '' ? array_map('trim', explode(',', $override)) : array(),
            'is_public'      => $access['is_public'],
            'membership_ids' => $access['membership_ids'],
            'plan_label'     => $access['plan_label'],
        );
    }

    public static function list_lessons(WP_REST_Request $request)
    {
        $q = new WP_Query(array(
            'post_type'      => SOCIO_COACH_LESSON_TYPE,
            'post_status'    => 'publish',
            'posts_per_page' => (int) $request['per_page'],
            'paged'          => (int) $request['page'],
            'orderby'        => 'ID',
            'order'          => 'ASC',
            'no_found_rows'  => false,
        ));
        return array(
            'lessons'     => array_map(array(__CLASS__, 'lesson_payload'), $q->posts),
            'total_pages' => max(1, (int) $q->max_num_pages),
        );
    }

    public static function get_lesson(WP_REST_Request $request)
    {
        $post = get_post((int) $request['id']);
        if (!$post || $post->post_type !== SOCIO_COACH_LESSON_TYPE || $post->post_status !== 'publish') {
            return new WP_Error('not_found', 'Lesson not found or not published', array('status' => 404));
        }
        return self::lesson_payload($post);
    }

    public static function token()
    {
        return array('token' => Socio_Coach_Token::for_current_user());
    }
}
