<?php
/**
 * Short-lived HS256 JWT telling the coach service who the logged-in member is.
 */

if (!defined('ABSPATH')) {
    exit;
}

class Socio_Coach_Token
{
    const LIFETIME = 600; // 10 minutes; the chat window refreshes it via REST.

    private static function b64url($data)
    {
        return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
    }

    /** Active MemberPress membership IDs for a user. */
    public static function active_memberships($user_id)
    {
        $ids = array();
        if (class_exists('MeprUser')) {
            $user = new MeprUser($user_id);
            if (method_exists($user, 'active_product_subscriptions')) {
                $ids = (array) $user->active_product_subscriptions('ids');
            }
        }
        $ids = array_values(array_unique(array_map('intval', $ids)));
        return apply_filters('socio_coach_member_memberships', $ids, $user_id);
    }

    public static function is_staff($user_id)
    {
        return (bool) apply_filters('socio_coach_is_staff', user_can($user_id, 'manage_options'), $user_id);
    }

    /** Returns the token, or '' when nobody is logged in or the secret is missing. */
    public static function for_current_user()
    {
        $user_id = get_current_user_id();
        $secret = Socio_Coach_Settings::get('member_token_secret');
        if (!$user_id || $secret === '') {
            return '';
        }
        $now = time();
        $header = array('alg' => 'HS256', 'typ' => 'JWT');
        $claims = array(
            'sub'         => (string) $user_id,
            'memberships' => self::active_memberships($user_id),
            'staff'       => self::is_staff($user_id),
            'iat'         => $now,
            'exp'         => $now + self::LIFETIME,
        );
        $signing_input = self::b64url(wp_json_encode($header)) . '.' . self::b64url(wp_json_encode($claims));
        $sig = hash_hmac('sha256', $signing_input, $secret, true);
        return $signing_input . '.' . self::b64url($sig);
    }
}
