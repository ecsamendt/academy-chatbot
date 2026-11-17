<?php
/**
 * Plugin Name: Socio AI Coach
 * Description: Chat window for the Socio AI Coach, member token signing, lesson timestamp links, and the content feed/webhooks the coach service uses.
 * Version: 0.1.0
 * Requires PHP: 7.4
 * Author: Su Socio de Negocios
 * Text Domain: socio-coach
 */

if (!defined('ABSPATH')) {
    exit;
}

define('SOCIO_COACH_VERSION', '0.1.0');
define('SOCIO_COACH_FILE', __FILE__);
define('SOCIO_COACH_DIR', plugin_dir_path(__FILE__));
define('SOCIO_COACH_URL', plugin_dir_url(__FILE__));

// MemberPress Courses post types. Filterable in case a site customizes them.
define('SOCIO_COACH_LESSON_TYPE', apply_filters('socio_coach_lesson_post_type', 'mpcs-lesson'));
define('SOCIO_COACH_COURSE_TYPE', apply_filters('socio_coach_course_post_type', 'mpcs-course'));

require_once SOCIO_COACH_DIR . 'includes/class-settings.php';
require_once SOCIO_COACH_DIR . 'includes/class-token.php';
require_once SOCIO_COACH_DIR . 'includes/class-access.php';
require_once SOCIO_COACH_DIR . 'includes/class-rest.php';
require_once SOCIO_COACH_DIR . 'includes/class-webhooks.php';
require_once SOCIO_COACH_DIR . 'includes/class-chat.php';
require_once SOCIO_COACH_DIR . 'includes/class-lesson-timestamps.php';

add_action('plugins_loaded', function () {
    Socio_Coach_Settings::init();
    Socio_Coach_Rest::init();
    Socio_Coach_Webhooks::init();
    Socio_Coach_Chat::init();
    Socio_Coach_Lesson_Timestamps::init();
});
