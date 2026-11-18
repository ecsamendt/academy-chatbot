<?php
/**
 * The chat window: [socio_coach] shortcode and the "Socio AI Coach" block.
 */

if (!defined('ABSPATH')) {
    exit;
}

class Socio_Coach_Chat
{
    public static function init()
    {
        add_shortcode('socio_coach', array(__CLASS__, 'render'));
        add_action('init', array(__CLASS__, 'register_block'));
    }

    public static function register_block()
    {
        wp_register_script(
            'socio-coach-block',
            SOCIO_COACH_URL . 'assets/block.js',
            array('wp-blocks', 'wp-element'),
            SOCIO_COACH_VERSION,
            true
        );
        register_block_type('socio-coach/chat', array(
            'editor_script'   => 'socio-coach-block',
            'render_callback' => array(__CLASS__, 'render'),
        ));
    }

    public static function render()
    {
        if (!is_user_logged_in()) {
            return '<div class="socio-coach socio-coach--locked">'
                . esc_html__('Inicia sesión para hablar con Socio, tu coach de negocios.', 'socio-coach')
                . '</div>';
        }
        wp_enqueue_style('socio-coach', SOCIO_COACH_URL . 'assets/chat.css', array(), SOCIO_COACH_VERSION);
        wp_enqueue_script('socio-coach', SOCIO_COACH_URL . 'assets/chat.js', array(), SOCIO_COACH_VERSION, true);
        // The member token is fetched by the script, never printed in the page,
        // so a page cache can't hand one member's token to someone else.
        wp_localize_script('socio-coach', 'SocioCoachConfig', array(
            'serviceUrl' => Socio_Coach_Settings::service_url(),
            'tokenUrl'   => rest_url(Socio_Coach_Rest::NS . '/token'),
            'nonce'      => wp_create_nonce('wp_rest'),
            'upgradeUrl' => apply_filters('socio_coach_upgrade_url', home_url('/planes/')),
        ));
        return '<div class="socio-coach" id="socio-coach" aria-live="polite"></div>';
    }
}
