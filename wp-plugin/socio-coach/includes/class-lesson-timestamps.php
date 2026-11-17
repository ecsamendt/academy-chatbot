<?php
/**
 * On lesson pages opened with ?t=<seconds>, jump the Vimeo player to that minute.
 */

if (!defined('ABSPATH')) {
    exit;
}

class Socio_Coach_Lesson_Timestamps
{
    public static function init()
    {
        add_action('wp_enqueue_scripts', array(__CLASS__, 'enqueue'));
    }

    public static function enqueue()
    {
        if (!is_singular(SOCIO_COACH_LESSON_TYPE) || !isset($_GET['t'])) {
            return;
        }
        wp_enqueue_script('vimeo-player', 'https://player.vimeo.com/api/player.js', array(), null, true);
        wp_enqueue_script('socio-coach-timestamps', SOCIO_COACH_URL . 'assets/lesson-timestamp.js',
            array('vimeo-player'), SOCIO_COACH_VERSION, true);
        wp_enqueue_style('socio-coach', SOCIO_COACH_URL . 'assets/chat.css', array(), SOCIO_COACH_VERSION);
    }
}
