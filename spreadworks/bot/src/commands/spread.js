const { SlashCommandBuilder, EmbedBuilder } = require('discord.js');

const API_URL = process.env.VITE_API_URL || 'http://localhost:8000';

module.exports = {
  data: new SlashCommandBuilder()
    .setName('spread')
    .setDescription('Get GEX levels and suggested strikes for a spread')
    .addStringOption((option) =>
      option
        .setName('symbol')
        .setDescription('Underlying symbol (default: SPY)')
        .setRequired(false)
    )
    .addStringOption((option) =>
      option
        .setName('strategy')
        .setDescription('Spread strategy type')
        .setRequired(false)
        .addChoices(
          { name: 'Double Diagonal', value: 'double_diagonal' },
          { name: 'Double Calendar', value: 'double_calendar' }
        )
    ),

  async execute(interaction) {
    await interaction.deferReply();

    const symbol = interaction.options.getString('symbol') || 'SPY';
    const strategy = interaction.options.getString('strategy') || 'double_diagonal';

    try {
      // Fetch GEX levels
      const gexRes = await fetch(`${API_URL}/api/spreadworks/gex?symbol=${symbol}`);
      if (!gexRes.ok) throw new Error(`GEX fetch failed: ${gexRes.status}`);
      const gexData = await gexRes.json();

      // Fetch suggested strikes
      const suggestRes = await fetch(
        `${API_URL}/api/spreadworks/gex-suggest?symbol=${symbol}&strategy=${strategy}`
      );
      if (!suggestRes.ok) throw new Error(`Suggestion fetch failed: ${suggestRes.status}`);
      const suggestion = await suggestRes.json();

      // Build GEX levels string
      const gexLines = [];
      if (gexData.flip_point) gexLines.push(`Flip Point: $${gexData.flip_point.toFixed(2)}`);
      if (gexData.call_wall) gexLines.push(`Call Wall: $${gexData.call_wall.toFixed(2)}`);
      if (gexData.put_wall) gexLines.push(`Put Wall: $${gexData.put_wall.toFixed(2)}`);
      if (gexData.gamma_regime) gexLines.push(`Regime: ${gexData.gamma_regime}`);

      // Build suggested strikes string
      const strikeLines = [];
      if (suggestion.legs) {
        const legs = suggestion.legs;
        if (strategy === 'double_diagonal') {
          strikeLines.push(`Long Put: $${legs.long_put_strike}`);
          strikeLines.push(`Short Put: $${legs.short_put_strike}`);
          strikeLines.push(`Short Call: $${legs.short_call_strike}`);
          strikeLines.push(`Long Call: $${legs.long_call_strike}`);
          strikeLines.push(`Short Exp: ${legs.short_expiration}`);
          strikeLines.push(`Long Exp: ${legs.long_expiration}`);
        } else {
          strikeLines.push(`Put Strike: $${legs.put_strike}`);
          strikeLines.push(`Call Strike: $${legs.call_strike}`);
          strikeLines.push(`Front Exp: ${legs.front_expiration}`);
          strikeLines.push(`Back Exp: ${legs.back_expiration}`);
        }
      }

      const strategyLabel =
        strategy === 'double_diagonal' ? 'Double Diagonal' : 'Double Calendar';

      const embed = new EmbedBuilder()
        .setTitle(`SpreadWorks: ${symbol} ${strategyLabel}`)
        .setColor(gexData.gamma_regime === 'POSITIVE' ? 0x22c55e : 0xef4444)
        .addFields(
          {
            name: 'GEX Levels',
            value: gexLines.length > 0 ? gexLines.join('\n') : 'No GEX data available',
            inline: true,
          },
          {
            name: 'Suggested Strikes',
            value: strikeLines.length > 0 ? strikeLines.join('\n') : 'No suggestion available',
            inline: true,
          }
        )
        .setTimestamp();

      if (suggestion.rationale) {
        embed.addFields({
          name: 'Rationale',
          value: suggestion.rationale,
          inline: false,
        });
      }

      if (suggestion.net_debit != null) {
        embed.setFooter({
          text: `Est. Net Debit: $${suggestion.net_debit.toFixed(2)}`,
        });
      }

      await interaction.editReply({ embeds: [embed] });
    } catch (error) {
      console.error('Spread command error:', error);
      await interaction.editReply({
        content: `Failed to fetch spread data for ${symbol}: ${error.message}`,
      });
    }
  },
};
