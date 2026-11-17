<?php
/**
 * Tells the coach service when a lesson is published, updated or removed so it re-indexes it.
 * Requests are non-blocking, so saving a lesson is never slowed down.
 */

if (!defined('ABSPATH')) {
    exit;
}

class Socio_Coach_Webhooks
{
    public static function init()
    {
        add_action('transition_post_status', array(__CLASS__, 'on_transition'), 10, 3);
        add_action('before_delete_post', array(__CLASS__, 'on_delete'));
    }

    public static function on_transition($new_status, $old_status, $post)
    {
        if ($post->post_type !== SOCIO_COACH_LESSON_TYPE || wp_is_post_revision($post) || wp_is_post_autosave($post)) {
            return;
        }
        if ($new_status === 'publish') {
            self::send($old_status === 'publish' ? 'lesson.updated' : 'lesson.published', $post->ID);
        } elseif ($old_status === 'publish') {
            self::send('lesson.deleted', $post->ID);
        }
    }

    public static function on_delete($post_id)
    {
        if (get_post_type($post_id) === SOCIO_COACH_LESSON_TYPE) {
            self::send('lesson.deleted', $post_id);
        }
    }

    public static function send($event, $lesson_id)
    {
        $secret = Socio_Coach_Settings::get('webhook_secret');
        $url = Socio_Coach_Settings::service_url('/webhooks/content');
        if ($secret === '' || $url === '/webhooks/content') {
            return;
        }
        $body = wp_json_encode(array('event' => $event, 'lesson_id' => (int) $lesson_id));
        wp_remote_post($url, array(
            'blocking' => false,
            'timeout'  => 5,
            'headers'  => array(
                'Content-Type'      => 'application/json',
                'X-Socio-Signature' => hash_hmac('sha256', $body, $secret),
            ),
            'body'     => $body,
        ));
    }
}
