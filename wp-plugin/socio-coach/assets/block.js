/* Editor side of the "Socio AI Coach" block. The front end is rendered by PHP. */
(function (blocks, element) {
  var el = element.createElement;
  blocks.registerBlockType('socio-coach/chat', {
    title: 'Socio AI Coach',
    icon: 'format-chat',
    category: 'widgets',
    supports: { html: false, multiple: false },
    edit: function () {
      return el(
        'div',
        { style: { padding: '16px', border: '1px dashed #999', borderRadius: '8px' } },
        'Socio AI Coach: the chat window appears here for logged-in members.'
      );
    },
    save: function () {
      return null;
    }
  });
})(window.wp.blocks, window.wp.element);
