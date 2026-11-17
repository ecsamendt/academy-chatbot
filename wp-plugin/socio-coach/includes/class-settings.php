<?php
/**
 * Settings screen (Settings > Socio AI Coach) and the staff re-index buttons.
 *
 * Secrets can also be set as constants in wp-config.php, which wins over the
 * database value and keeps secrets out of the options table:
 *   define('SOCIO_COACH_MEMBER_TOKEN_SECRET', '...');
 */

if (!defined('ABSPATH')) {
    exit;
}

class Socio_Coach_Settings
{
    const OPTION = 'socio_coach_settings';

    const FIELDS = array(
        'service_url'         => 'Coach service URL',
        'member_token_secret' => 'Member token secret',
        'webhook_secret'      => 'Webhook secret',
        'ingest_secret'       => 'Ingest secret',
        'admin_api_key'       => 'Admin API key',
    );

    const SECRET_FIELDS = array('member_token_secret', 'webhook_secret', 'ingest_secret', 'admin_api_key');

    public static function init()
    {
        add_action('admin_menu', array(__CLASS__, 'menu'));
        add_action('admin_init', array(__CLASS__, 'register'));
        add_action('admin_post_socio_coach_reindex', array(__CLASS__, 'handle_reindex'));
    }

    public static function get($key)
    {
        $const = 'SOCIO_COACH_' . strtoupper($key);
        if (defined($const)) {
            return (string) constant($const);
        }
        $opts = get_option(self::OPTION, array());
        return isset($opts[$key]) ? (string) $opts[$key] : '';
    }

    public static function service_url($path = '')
    {
        return rtrim(self::get('service_url'), '/') . $path;
    }

    public static function menu()
    {
        add_options_page('Socio AI Coach', 'Socio AI Coach', 'manage_options', 'socio-coach', array(__CLASS__, 'render'));
    }

    public static function register()
    {
        register_setting('socio_coach', self::OPTION, array(
            'type'              => 'array',
            'sanitize_callback' => array(__CLASS__, 'sanitize'),
        ));
        add_settings_section('socio_coach_main', '', '__return_false', 'socio-coach');
        foreach (self::FIELDS as $key => $label) {
            add_settings_field($key, esc_html($label), array(__CLASS__, 'field'), 'socio-coach', 'socio_coach_main', array('key' => $key));
        }
    }

    public static function sanitize($input)
    {
        $old = get_option(self::OPTION, array());
        $out = array();
        foreach (array_keys(self::FIELDS) as $key) {
            $val = isset($input[$key]) ? trim((string) $input[$key]) : '';
            // Leaving a secret field blank keeps the stored value.
            if ($val === '' && in_array($key, self::SECRET_FIELDS, true) && isset($old[$key])) {
                $val = $old[$key];
            }
            $out[$key] = $key === 'service_url' ? esc_url_raw($val) : sanitize_text_field($val);
        }
        return $out;
    }

    public static function field($args)
    {
        $key = $args['key'];
        $is_secret = in_array($key, self::SECRET_FIELDS, true);
        $name = esc_attr(self::OPTION . '[' . $key . ']');
        if (defined('SOCIO_COACH_' . strtoupper($key))) {
            echo '<em>Set in wp-config.php</em>';
            return;
        }
        if ($is_secret) {
            $has = self::get($key) !== '';
            printf('<input type="password" class="regular-text" name="%s" value="" autocomplete="new-password" placeholder="%s" />',
                $name, $has ? esc_attr__('(saved - leave blank to keep)', 'socio-coach') : '');
        } else {
            printf('<input type="url" class="regular-text" name="%s" value="%s" placeholder="https://coach.example.com" />',
                $name, esc_attr(self::get($key)));
        }
    }

    public static function render()
    {
        if (!current_user_can('manage_options')) {
            return;
        }
        $notice = isset($_GET['socio_notice']) ? sanitize_text_field(wp_unslash($_GET['socio_notice'])) : '';
        ?>
        <div class="wrap">
            <h1>Socio AI Coach</h1>
            <?php if ($notice) : ?>
                <div class="notice notice-info"><p><?php echo esc_html($notice); ?></p></div>
            <?php endif; ?>
            <p>Add the chat window to any page with the <code>[socio_coach]</code> shortcode or the <strong>Socio AI Coach</strong> block.</p>
            <form method="post" action="options.php">
                <?php
                settings_fields('socio_coach');
                do_settings_sections('socio-coach');
                submit_button();
                ?>
            </form>
            <h2>Re-index content</h2>
            <p>Lessons re-index automatically when published or updated. Use these for manual fixes.</p>
            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
                <input type="hidden" name="action" value="socio_coach_reindex" />
                <?php wp_nonce_field('socio_coach_reindex'); ?>
                <button class="button" name="what" value="all">Re-index all lessons</button>
                <button class="button" name="what" value="tools">Re-index tools</button>
                <input type="number" name="lesson_id" placeholder="Lesson ID" min="1" style="width:110px" />
                <button class="button" name="what" value="lesson">Re-index lesson</button>
            </form>
        </div>
        <?php
    }

    public static function handle_reindex()
    {
        if (!current_user_can('manage_options')) {
            wp_die('Forbidden', 403);
        }
        check_admin_referer('socio_coach_reindex');
        $what = isset($_POST['what']) ? sanitize_key(wp_unslash($_POST['what'])) : '';
        $body = array();
        if ($what === 'all') {
            $body['all'] = true;
        } elseif ($what === 'tools') {
            $body['tools'] = true;
        } elseif ($what === 'lesson' && !empty($_POST['lesson_id'])) {
            $body['lesson_id'] = absint($_POST['lesson_id']);
        }
        $notice = 'Nothing to re-index.';
        if ($body) {
            $res = wp_remote_post(self::service_url('/admin/reindex'), array(
                'timeout' => 15,
                'headers' => array('Content-Type' => 'application/json', 'X-Admin-Key' => self::get('admin_api_key')),
                'body'    => wp_json_encode($body),
            ));
            if (is_wp_error($res)) {
                $notice = 'Could not reach the coach service: ' . $res->get_error_message();
            } elseif (wp_remote_retrieve_response_code($res) !== 200) {
                $notice = 'Coach service returned HTTP ' . wp_remote_retrieve_response_code($res) . '.';
            } else {
                $notice = 'Re-index queued. Transcription can take a few minutes per lesson.';
            }
        }
        wp_safe_redirect(add_query_arg('socio_notice', rawurlencode($notice), admin_url('options-general.php?page=socio-coach')));
        exit;
    }
}
